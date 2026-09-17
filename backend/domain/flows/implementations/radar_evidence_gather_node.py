"""
展厅发觉：证据采集 Function 节点

按 planner 产出的 queries，节点内 asyncio.gather 并行调用博查 + AnySearch
（知识库开关开启时**并列**加挂 Milvus 知识库检索，见 01 文档 §3.3 / 03 文档 T2.3），
压缩为 evidence_briefs / discarded_briefs **仅写入 prompt_vars 一份**，供终评占位符使用；
避免在 edges_var / persistence / flow_msgs 中重复塞同一份全量列表。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from langchain_core.tools import BaseTool

from backend.domain.flows.nodes.base_function import BaseFunctionNode
from backend.domain.state import FlowState
from backend.domain.tools.bocha_tool import bocha_web_search
from backend.domain.tools.anysearch_tool import anysearch_web_search, anysearch_extract
from backend.domain.tools.huayuan_radar_event_context import (
    MAX_KNOWLEDGE_DOCS_LIMIT,
    extract_source_host,
    get_huayuan_radar_event_context,
    text_mentions_subject,
)
from backend.app.config import settings
from backend.domain.news_content.chunking import strip_title_prefix
from backend.infrastructure.observability.langfuse_handler import record_observation_span

logger = logging.getLogger(__name__)

# 知识库召回条目的契约字段（与 app/api/schemas/huayuan_radar_event.py 的常量保持一致）
_KNOWLEDGE_TOOL_NAME = "knowledge_base"
_KNOWLEDGE_SOURCE_LEVEL = "P0"
# 知识库召回条目在 briefs 中的来源权威档（公司官网新闻）
_KNOWLEDGE_AUTHORITY_TIER = "company_official"


async def invoke_registered_tool(tool_obj: Any, payload: Dict[str, Any]) -> str:
    """
        调用 @register_tool 装饰后的 StructuredTool（不可直接当协程函数调用）。

        Args:
            tool_obj: BaseTool / StructuredTool 实例
            payload: 工具入参字典

        Returns:
            工具返回的字符串（通常为 JSON）
    """
    if isinstance(tool_obj, BaseTool):
        raw = await tool_obj.ainvoke(payload)
    elif callable(tool_obj):
        raw = tool_obj(**payload)
        if hasattr(raw, "__await__"):
            raw = await raw
    else:
        raise TypeError(f"工具不可调用: type={type(tool_obj).__name__}")
    return raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)

_MAX_QUERIES = 5
_MIN_QUERIES_HINT = 3
_SUMMARY_MAX_CHARS = 200
_MAX_BRIEFS = 40
_MAX_BRIEFS_FOR_PROMPT = 12
_MAX_DISCARDED_FOR_PROMPT = 15
_MAX_EXTRACT_CANDIDATES = 5
_INVALID_MARKERS = (
    "Example Domain",
    "404 Not Found",
    "404",
    "Access Denied",
    "Just a moment",
    "验证码",
    "请开启JavaScript",
)
_ACTION_HINT_KEYWORDS = (
    "招标",
    "采购",
    "立项",
    "展厅",
    "展馆",
    "展示中心",
    "展陈",
    "改造",
    "装修",
    "企业馆",
    "体验中心",
)


def _brief_priority(brief: Dict[str, Any]) -> tuple:
    """
        终评入模排序：知识库（P0）优先，其次主体命中，再次含动作/空间关键词与 quote。

        注：知识库未开启时 briefs 中不存在 knowledge_base 条目，排序结果与改造前一致。

        Args:
            brief: 单条 brief

        Returns:
            可比较的排序键（越大越优先，配合 reverse=True）
    """
    text = " ".join(
        [
            str(brief.get("title") or ""),
            str(brief.get("summary") or ""),
            str(brief.get("quote") or ""),
        ]
    )
    kw_hits = sum(1 for kw in _ACTION_HINT_KEYWORDS if kw in text)
    return (
        1 if brief.get("tool_name") == _KNOWLEDGE_TOOL_NAME else 0,
        1 if brief.get("subject_match") else 0,
        kw_hits,
        1 if brief.get("quote") else 0,
        1 if brief.get("authority_tier") in ("regulator_or_exchange", "gov") else 0,
    )


def _compact_briefs_for_prompt(briefs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
        压缩写入终评 prompt 的 briefs：排序截断，去掉冗余字段。

        Args:
            briefs: 全量 briefs

        Returns:
            精简后的列表
    """
    ranked = sorted(briefs, key=_brief_priority, reverse=True)
    selected = ranked[:_MAX_BRIEFS_FOR_PROMPT]
    compact: List[Dict[str, Any]] = []
    for b in selected:
        item = {
            "title": b.get("title"),
            "url": b.get("url"),
            "summary": _clip(str(b.get("summary") or ""), 160),
            "quote": _clip(str(b.get("quote") or ""), 160) or None,
            "why_evidential": _clip(str(b.get("why_evidential") or ""), 120),
            "tool_name": b.get("tool_name"),
            "source_host": b.get("source_host"),
            "subject_match": bool(b.get("subject_match")),
            "query": b.get("query"),
        }
        # 知识库条目额外带 doc_id / source_level / score：
        # doc_id 供 load_news_document 按需拉全文（白名单），source_level 供 evidences 落库
        if b.get("doc_id"):
            item["doc_id"] = str(b.get("doc_id"))
            # 知识库 quote 用策略 C 配置长度，避免压成 160 字丢掉命中片段
            item["quote"] = (
                _clip(
                    str(b.get("quote") or ""),
                    int(settings.KNOWLEDGE_BRIEF_QUOTE_MAX_CHARS),
                )
                or None
            )
        if b.get("source_level"):
            item["source_level"] = b.get("source_level")
        if b.get("score") is not None:
            item["score"] = b.get("score")
        if b.get("content_grade"):
            item["content_grade"] = b.get("content_grade")
        if b.get("source_kind"):
            item["source_kind"] = b.get("source_kind")
        compact.append(item)
    return compact


def _compact_discarded_for_prompt(
    discarded: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
        压缩 discarded：优先保留带 URL 的条目，限制条数与 reason 长度。

        Args:
            discarded: 全量 discarded

        Returns:
            精简列表
    """
    with_url = [d for d in discarded if d.get("url")]
    without_url = [d for d in discarded if not d.get("url")]
    merged = with_url + without_url
    out: List[Dict[str, Any]] = []
    for d in merged[:_MAX_DISCARDED_FOR_PROMPT]:
        out.append(
            {
                "title": d.get("title"),
                "url": d.get("url"),
                "reason": _clip(str(d.get("reason") or ""), 100),
            }
        )
    return out


def _clip(text: str, limit: int = _SUMMARY_MAX_CHARS) -> str:
    """截断文本。"""
    s = str(text or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit]


def _is_invalid_content(text: str) -> bool:
    """判断抽取/摘要是否为无效页特征。"""
    blob = str(text or "")
    if not blob.strip():
        return False
    for marker in _INVALID_MARKERS:
        if marker in blob:
            # 「404」过短，要求作为独立片段出现时再判无效
            if marker == "404" and "404" not in blob[:80] and "Not Found" not in blob:
                continue
            return True
    return False


def _why_evidential(item: Dict[str, Any], query: str) -> str:
    """
        生成简短「为何可作证据」说明（启发式，终评可再判）。

        Args:
            item: 单条搜索 enrichment 结果
            query: 命中检索式

        Returns:
            一句话理由
    """
    parts: List[str] = []
    tool = str(item.get("tool_name") or "")
    if tool:
        parts.append(f"来源工具 {tool}")
    if item.get("subject_match"):
        parts.append("摘要含公司主体词")
    host = item.get("source_host") or ""
    if host:
        parts.append(f"站点 {host}")
    if query:
        parts.append(f"命中检索「{_clip(query, 40)}」")
    title = str(item.get("title") or "")
    for kw in ("招标", "采购", "立项", "展厅", "展馆", "展示中心", "展陈", "改造", "装修"):
        if kw in title or kw in str(item.get("snippet") or "") or kw in str(item.get("summary") or ""):
            parts.append(f"含关键词「{kw}」")
            break
    return "；".join(parts) if parts else "搜索命中，待终评核对"


def _parse_tool_json(raw: str) -> Dict[str, Any]:
    """解析工具返回 JSON；失败返回 ok=False。"""
    try:
        obj = json.loads(raw) if isinstance(raw, str) else {}
        return obj if isinstance(obj, dict) else {"ok": False, "error": "非对象 JSON"}
    except Exception as e:
        return {"ok": False, "error": f"JSON 解析失败: {e}"}


def _normalize_queries(
    raw_queries: Any,
    company_name: str,
) -> List[str]:
    """
        规范化 planner 输出的 query 列表：去空、去重、最多 5 条；空则兜底。

        Args:
            raw_queries: edges_var / persistence 中的 queries
            company_name: 公司名（兜底用）

        Returns:
            检索式列表
    """
    out: List[str] = []
    seen: Set[str] = set()
    if isinstance(raw_queries, list):
        for q in raw_queries:
            s = str(q or "").strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
            if len(out) >= _MAX_QUERIES:
                break
    if out:
        return out
    # 兜底：保证采集节点仍可跑
    name = (company_name or "").strip() or "目标公司"
    c = f'"{name}"'
    return [f"{c} 展厅", f"{c} 展示中心", f"{c} 展厅 招标"]


def _read_queries_from_state(state: FlowState) -> Tuple[List[str], str]:
    """
        从 edges_var / persistence_edges_var 读取 queries 与公司名。

        Args:
            state: 流程状态

        Returns:
            (queries, company_name)
    """
    edges = state.get("edges_var") or {}
    persistence = state.get("persistence_edges_var") or {}
    prompt_vars = state.get("prompt_vars") or {}

    raw_queries = edges.get("queries")
    if raw_queries is None:
        raw_queries = persistence.get("queries")

    company_name = ""
    company_json = prompt_vars.get("company_json") or ""
    if isinstance(company_json, str) and company_json.strip().startswith("{"):
        try:
            company_obj = json.loads(company_json)
            if isinstance(company_obj, dict):
                company_name = str(company_obj.get("company_name") or "")
        except Exception:
            pass
    ctx = get_huayuan_radar_event_context()
    if ctx and ctx.company_name:
        company_name = ctx.company_name

    return _normalize_queries(raw_queries, company_name), company_name


class EvidenceGatherNode(BaseFunctionNode):
    """按 query 并行多源搜索并压缩为 evidence_briefs。"""

    @classmethod
    def get_key(cls) -> str:
        """返回节点的唯一标识 key。"""
        return "radar_evidence_gather_func"

    async def _search_one(self, tool_name: str, query: str) -> Dict[str, Any]:
        """
            调用单个搜索工具并解析结果。

            Args:
                tool_name: bocha_web_search / anysearch_web_search
                query: 检索式

            Returns:
                含 ok/results/tool_name/query 的字典
        """
        # @register_tool 返回 StructuredTool，必须 ainvoke，不能当协程函数直接调用
        tool_obj = (
            bocha_web_search if tool_name == "bocha_web_search" else anysearch_web_search
        )
        raw = await invoke_registered_tool(
            tool_obj, {"query": query, "max_results": 0}
        )
        payload = _parse_tool_json(raw)
        payload["tool_name"] = tool_name
        payload["query"] = query
        return payload

    async def _knowledge_search_one(self, query: str) -> Dict[str, Any]:
        """
            单条 query 的知识库检索：query embedding（bge-m3，同写链路模型）→ Milvus 检索。

            降级约定：任何失败都返回 `ok=False`（不抛异常），由调用方跳过该 query，
            主链路（博查/AnySearch/终评）不受影响。

            Args:
                query: 检索式

            Returns:
                含 ok/results/query/error 的字典；results 项为
                {"doc_id","title","summary","url","score"}
        """
        payload: Dict[str, Any] = {
            "ok": False,
            "query": query,
            "results": [],
            "error": "",
        }
        ctx = get_huayuan_radar_event_context()
        if ctx is None or not ctx.knowledge.enabled:
            payload["error"] = "知识库未启用"
            return payload
        if ctx.company_id is None:
            # 缺 company_id 时不过滤会跨企业召回（幻觉/串证据风险），宁可跳过
            payload["error"] = "缺少 company_id，已跳过知识库检索（避免跨企业召回）"
            return payload

        max_docs = max(1, min(MAX_KNOWLEDGE_DOCS_LIMIT, int(ctx.knowledge.max_docs)))
        factor = max(1, int(settings.KNOWLEDGE_SEARCH_CHUNK_TOP_K_FACTOR))
        # 候选按 chunk 放大，减轻长文占满 topK（策略 C）
        top_k = min(128, max(max_docs * factor, max_docs + 8))
        # 延迟导入：开关关闭的请求完全不加载 pymilvus / embedding 依赖
        try:
            from backend.infrastructure.llm.huayuan_embedding_client import (
                HuayuanEmbeddingClient,
            )
            from backend.infrastructure.milvus import get_milvus_store

            embedder = HuayuanEmbeddingClient()
            try:
                vector = await embedder.embed_one(query)
            finally:
                await embedder.aclose()
            store = get_milvus_store()
            per_path = max(4, top_k // 2)
            full_hits = await store.search_async(
                vector, company_id=int(ctx.company_id), content_grade="full", top_k=per_path
            )
            stub_hits = await store.search_async(
                vector, company_id=int(ctx.company_id), content_grade="stub", top_k=per_path
            )
            merged: dict[str, dict[str, Any]] = {}
            for hit in (full_hits or []) + (stub_hits or []):
                if not isinstance(hit, dict):
                    continue
                key = str(hit.get("chunk_id") or hit.get("doc_id") or "")
                prev = merged.get(key)
                if prev is None or float(hit.get("score") or 0) > float(prev.get("score") or 0):
                    merged[key] = hit
            hits = sorted(
                merged.values(),
                key=lambda h: float(h.get("score") or 0),
                reverse=True,
            )[:top_k]
        except Exception as e:
            payload["error"] = f"{type(e).__name__}: {e}"
            return payload

        payload["ok"] = True
        payload["results"] = [h for h in (hits or []) if isinstance(h, dict)]
        return payload

    def _merge_knowledge_results(
        self,
        ctx: Any,
        knowledge_queries: List[str],
        knowledge_results: List[Any],
        briefs: List[Dict[str, Any]],
        discarded: List[Dict[str, Any]],
        seen_urls: Set[str],
    ) -> None:
        """
            合并知识库检索结果：去重后按相似度取 top max_docs 并入 briefs（P0），
            记录召回白名单，并输出命中率日志 + Langfuse 观测。

            ⚠️ 「检索调用失败」与「调用成功但零命中」必须在日志/观测里可区分
            （01 文档 §8 风险 9），否则无法判断「知识库没用」还是「知识库没接上」。

            Args:
                ctx: 规则二请求上下文
                knowledge_queries: 本次知识库检索的 query 列表
                knowledge_results: 与 queries 对齐的检索结果（或异常）
                briefs: 可变 briefs 列表（知识库条目 append 在前）
                discarded: 可变 discarded 列表（检索降级时补一条可读原因）
                seen_urls: URL 去重集合（与两源共用）
        """
        knowledge = ctx.knowledge
        candidates: List[Tuple[float, Dict[str, Any], str]] = []
        first_error = ""
        failed_queries = 0
        # 先按相似度取 top max_docs，再与两源去重合并（对齐 03 文档 T2.3）
        max_docs = max(1, min(MAX_KNOWLEDGE_DOCS_LIMIT, int(knowledge.max_docs)))

        for query, result in zip(knowledge_queries, knowledge_results):
            if isinstance(result, Exception):
                knowledge.mark_recall_result(hit_count=0, failed=True)
                failed_queries += 1
                first_error = first_error or f"{type(result).__name__}: {result}"
                continue
            if not result.get("ok"):
                knowledge.mark_recall_result(hit_count=0, failed=True)
                failed_queries += 1
                first_error = first_error or str(result.get("error") or "未知错误")
                continue
            hits = [h for h in (result.get("results") or []) if isinstance(h, dict)]
            # 检索调用成功：命中数决定「命中」还是「零命中」（两者都计入命中率分母）
            knowledge.mark_recall_result(hit_count=len(hits))
            for hit in hits:
                if not str(hit.get("doc_id") or "").strip():
                    continue
                try:
                    score_value = float(hit.get("score"))
                except (TypeError, ValueError):
                    score_value = 0.0
                candidates.append((score_value, hit, query))

        # 1. 按 score 降序，为每个 doc 保留 best / second（second 需 index 间隔≥2）
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_by_doc: Dict[str, Dict[str, Any]] = {}
        for score_value, hit, query in candidates:
            doc_id = str(hit.get("doc_id") or "").strip()
            entry = best_by_doc.get(doc_id)
            if entry is None:
                best_by_doc[doc_id] = {
                    "best": hit,
                    "best_score": score_value,
                    "second": None,
                    "second_score": None,
                    "query": query,
                }
                continue
            if entry.get("second") is not None:
                continue
            if not self._can_attach_second_chunk(
                entry["best"], hit, entry["best_score"], score_value
            ):
                continue
            entry["second"] = hit
            entry["second_score"] = score_value

        # 2. 按 best.score 取文档，URL 去重
        ranked_docs = sorted(
            best_by_doc.items(),
            key=lambda kv: float(kv[1]["best_score"]),
            reverse=True,
        )
        merged: List[Dict[str, Any]] = []
        merged_doc_ids: List[str] = []
        for doc_id, entry in ranked_docs:
            if len(merged) >= max_docs:
                break
            hit = entry["best"]
            url = str(hit.get("url") or "").strip()
            if not url.startswith("http") or url in seen_urls:
                continue
            seen_urls.add(url)
            merged.append(
                self._knowledge_brief(
                    hit,
                    entry["query"],
                    ctx.subject_keywords(),
                    second_hit=entry.get("second"),
                    second_score=entry.get("second_score"),
                )
            )
            merged_doc_ids.append(doc_id)

        briefs.extend(merged)
        knowledge.register_recalled(merged_doc_ids)

        if failed_queries:
            discarded.append(
                {
                    "title": None,
                    "url": None,
                    "reason": (
                        f"知识库检索降级跳过（{failed_queries}/{len(knowledge_queries)} 条 query）："
                        f"{first_error}"
                    ),
                }
            )

        logger.info(
            f"[evidence_gather][knowledge] 召回统计 "
            f"queries={knowledge.recall_query_count}, "
            f"命中query={knowledge.recall_hit_queries}, "
            f"零命中query={knowledge.recall_zero_hit_queries}, "
            f"检索失败query={knowledge.recall_error_queries}, "
            f"命中率={knowledge.hit_rate:.2f}, "
            f"候选chunk={len(candidates)}, 聚合doc={len(best_by_doc)}, "
            f"并入briefs={len(merged)}/{max_docs}, "
            f"白名单={len(knowledge.recalled_doc_ids)}"
        )
        if knowledge.recall_query_count and knowledge.recall_hit_queries == 0:
            logger.warning(
                f"[evidence_gather][knowledge] 本次检索零命中："
                f"失败query={knowledge.recall_error_queries}（0=调用成功但知识库内无该公司文档）；"
                f"first_error={first_error or '(无)'}"
            )

        record_observation_span(
            "knowledge_base_recall",
            input_data={
                "queries": knowledge_queries,
                "company_id": ctx.company_id,
                "max_docs": max_docs,
            },
            output_data={
                "recall_query_count": knowledge.recall_query_count,
                "hit_queries": knowledge.recall_hit_queries,
                "zero_hit_queries": knowledge.recall_zero_hit_queries,
                "error_queries": knowledge.recall_error_queries,
                "hit_rate": round(knowledge.hit_rate, 4),
                "candidate_chunks": len(candidates),
                "aggregated_docs": len(best_by_doc),
                "merged_briefs": len(merged),
                "whitelist_size": len(knowledge.recalled_doc_ids),
            },
            metadata={
                "flow": "huayuan_radar_event_agent",
                "tool_name": _KNOWLEDGE_TOOL_NAME,
                "source_level": _KNOWLEDGE_SOURCE_LEVEL,
                "failed_queries": failed_queries,
                "first_error": first_error[:200],
            },
            trace_id=(ctx.trace_id or None),
            level=(
                "WARNING"
                if knowledge.recall_query_count and knowledge.recall_hit_queries == 0
                else None
            ),
        )

    @staticmethod
    def _can_attach_second_chunk(
        best: Dict[str, Any],
        candidate: Dict[str, Any],
        best_score: float,
        cand_score: float,
    ) -> bool:
        """判断次优 chunk 是否可附到同一 brief（分数接近且 index 间隔≥2）。"""
        if not bool(settings.KNOWLEDGE_BRIEF_SECOND_CHUNK_ENABLED):
            return False
        close = cand_score >= best_score * 0.95 or abs(best_score - cand_score) < 0.03
        if not close:
            return False
        try:
            i1 = int(best.get("chunk_index"))
            i2 = int(candidate.get("chunk_index"))
        except (TypeError, ValueError):
            return False
        return abs(i1 - i2) >= 2

    def _knowledge_brief(
        self,
        hit: Dict[str, Any],
        query: str,
        subject_keywords: List[str],
        *,
        second_hit: Optional[Dict[str, Any]] = None,
        second_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
            将文档级聚合命中转为 brief（注入最佳 chunk 的 quote）。

            Args:
                hit: 最高分 chunk
                query: 命中的检索式
                subject_keywords: 公司主体关键词
                second_hit: 可选第二段 chunk
                second_score: 第二段分数

            Returns:
                brief 字典
        """
        doc_id = str(hit.get("doc_id") or "").strip()
        title = hit.get("title")
        summary = _clip(str(hit.get("summary") or ""))
        url = str(hit.get("url") or "").strip()
        score = hit.get("score")
        try:
            score_text = f"{float(score):.3f}"
        except (TypeError, ValueError):
            score_text = "未知"

        quote_limit = int(settings.KNOWLEDGE_BRIEF_QUOTE_MAX_CHARS)
        quote_body = strip_title_prefix(str(hit.get("embed_text") or ""), title)
        quote = _clip(quote_body, quote_limit)
        if second_hit is not None:
            second_body = strip_title_prefix(
                str(second_hit.get("embed_text") or ""), title
            )
            second_clip = _clip(second_body, max(80, quote_limit // 2))
            if second_clip:
                quote = f"{quote}\n【相关段落2】{second_clip}" if quote else second_clip

        try:
            chunk_index = int(hit.get("chunk_index"))
        except (TypeError, ValueError):
            chunk_index = -1
        try:
            chunk_count = int(hit.get("chunk_count"))
        except (TypeError, ValueError):
            chunk_count = 0
        chunk_label = (
            f"命中第 {chunk_index + 1}/{chunk_count} 段"
            if chunk_index >= 0 and chunk_count > 0
            else "命中知识库分段"
        )
        why = (
            f"公司新闻知识库召回，相似度 {score_text}；{chunk_label}；"
            f"doc_id={doc_id}（可用 load_news_document 拉全文核对原文）"
        )
        if second_hit is not None and second_score is not None:
            try:
                why += (
                    f"；附带第 {int(second_hit.get('chunk_index')) + 1} 段"
                    f"（{float(second_score):.3f}）"
                )
            except (TypeError, ValueError):
                why += "；附带相关段落2"

        subject_blob = f"{title or ''}\n{summary}\n{quote}"
        return {
            "title": title,
            "url": url,
            "summary": summary,
            "quote": quote or None,
            "why_evidential": why,
            "tool_name": _KNOWLEDGE_TOOL_NAME,
            "source_level": _KNOWLEDGE_SOURCE_LEVEL,
            "doc_id": doc_id,
            "score": score,
            "publish_date": None,
            "source_host": extract_source_host(url),
            "authority_tier": _KNOWLEDGE_AUTHORITY_TIER,
            "subject_match": text_mentions_subject(subject_blob, subject_keywords),
            "query": query,
            "chunk_index": chunk_index if chunk_index >= 0 else None,
            "content_grade": hit.get("content_grade"),
            "source_kind": hit.get("source_kind"),
        }

    async def _maybe_extract(
        self,
        briefs: List[Dict[str, Any]],
        discarded: List[Dict[str, Any]],
    ) -> None:
        """
            对主体命中但摘要偏短的 Top-N URL 做正文抽取，回填 quote。

            Args:
                briefs: 可变 briefs 列表
                discarded: 可变 discarded 列表
        """
        candidates = [
            b
            for b in briefs
            if b.get("url")
            and not b.get("quote")
            # 知识库条目走 load_news_document 按需拉全文，不占用 anysearch 抽取配额
            and b.get("tool_name") != _KNOWLEDGE_TOOL_NAME
            and len(str(b.get("summary") or "")) < 80
        ][:_MAX_EXTRACT_CANDIDATES]
        if not candidates:
            return

        import asyncio

        async def _one(brief: Dict[str, Any]) -> None:
            url = str(brief.get("url") or "")
            raw = await invoke_registered_tool(anysearch_extract, {"url": url})
            payload = _parse_tool_json(raw)
            if not payload.get("ok"):
                discarded.append(
                    {
                        "title": brief.get("title"),
                        "url": url,
                        "reason": f"抽取失败: {payload.get('error')}",
                    }
                )
                return
            content = str(payload.get("content") or "")
            if _is_invalid_content(content):
                discarded.append(
                    {
                        "title": brief.get("title"),
                        "url": url,
                        "reason": "抽取正文为无效页（占位/404/验证码等）",
                    }
                )
                return
            brief["quote"] = _clip(content)
            if not brief.get("summary"):
                brief["summary"] = _clip(content)

        await asyncio.gather(*[_one(b) for b in candidates])

    async def execute(self, state: FlowState) -> FlowState:
        """
            并行采集证据；压缩结果只写入 prompt_vars（一份），供终评占位符。

            Args:
                state: 流程状态

            Returns:
                更新后的状态
        """
        import asyncio

        # 1. 读取并规范化 queries
        queries, company_name = _read_queries_from_state(state)
        logger.info(
            f"[evidence_gather] company={company_name}, queries={len(queries)}"
        )

        # 1.1 规划阶段广搜会占用「已搜 query」去重；采集需按规划式重新搜，
        #     故清空去重集合但保留计数（配额仍累计规划阶段消耗）。
        ctx = get_huayuan_radar_event_context()
        if ctx is not None:
            with ctx._lock:
                ctx.searched_bocha_queries.clear()
                ctx.searched_anysearch_queries.clear()
                # extracted_urls 保留，避免对规划阶段已抽 URL 重复抽取
            logger.info(
                f"[evidence_gather] 已清空搜索去重集，当前计数 "
                f"bocha={ctx.bocha_count}/{ctx.max_bocha}, "
                f"anysearch={ctx.anysearch_count}/{ctx.max_anysearch}"
            )

        # 2. 构造并行任务：每条 query ×（博查 + AnySearch）[+ 知识库检索（开关开时）]
        tasks_meta: List[Tuple[str, str]] = []
        coros = []
        for q in queries:
            for tool_name in ("bocha_web_search", "anysearch_web_search"):
                tasks_meta.append((tool_name, q))
                coros.append(self._search_one(tool_name, q))

        web_task_count = len(coros)
        knowledge_enabled = bool(ctx is not None and ctx.knowledge.enabled)
        knowledge_queries: List[str] = []
        if knowledge_enabled:
            # 知识库检索与两源搜索**并列**（同一个 gather 内并行，互不阻塞）
            for q in queries:
                knowledge_queries.append(q)
                coros.append(self._knowledge_search_one(q))
            logger.info(
                f"[evidence_gather][knowledge] 已并列挂载知识库检索 "
                f"queries={len(knowledge_queries)}, company_id={ctx.company_id}, "
                f"max_docs={ctx.knowledge.max_docs}, "
                f"max_load_times={ctx.knowledge.max_load_times}"
            )
        else:
            logger.info("[evidence_gather][knowledge] 知识库开关关闭，本次不做任何 Milvus 检索")

        results = await asyncio.gather(*coros, return_exceptions=True)
        web_results = results[:web_task_count]
        knowledge_results = results[web_task_count:]

        # 3. 归一为 briefs / discarded，URL 去重
        briefs: List[Dict[str, Any]] = []
        discarded: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()

        # 3.1 知识库条目优先入 briefs（P0 优先保住配额）；召回 doc_id 记入白名单
        if knowledge_enabled and ctx is not None:
            self._merge_knowledge_results(
                ctx, knowledge_queries, knowledge_results, briefs, discarded, seen_urls
            )

        # 3.2 两源搜索结果（与知识库条目按 URL 去重，重复的跳过）
        for meta, result in zip(tasks_meta, web_results):
            tool_name, query = meta
            if isinstance(result, Exception):
                discarded.append(
                    {
                        "title": None,
                        "url": None,
                        "reason": f"{tool_name} 异常: {result}",
                    }
                )
                continue
            if not result.get("ok"):
                discarded.append(
                    {
                        "title": None,
                        "url": None,
                        "reason": f"{tool_name}@{query[:40]}: {result.get('error')}",
                    }
                )
                continue
            for item in result.get("results") or []:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if not url or not url.startswith("http"):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                summary_src = (
                    item.get("summary")
                    or item.get("snippet")
                    or item.get("content")
                    or ""
                )
                summary = _clip(str(summary_src))
                if _is_invalid_content(summary):
                    discarded.append(
                        {
                            "title": item.get("title"),
                            "url": url,
                            "reason": "摘要疑似无效页",
                        }
                    )
                    continue
                item_with_tool = {**item, "tool_name": tool_name}
                briefs.append(
                    {
                        "title": item.get("title"),
                        "url": url,
                        "summary": summary,
                        "quote": None,
                        "why_evidential": _why_evidential(item_with_tool, query),
                        "tool_name": tool_name,
                        "publish_date": item.get("publish_date"),
                        "source_host": item.get("source_host") or extract_source_host(url),
                        "authority_tier": item.get("authority_tier"),
                        "subject_match": bool(item.get("subject_match")),
                        "query": query,
                    }
                )
                if len(briefs) >= _MAX_BRIEFS:
                    break
            if len(briefs) >= _MAX_BRIEFS:
                break

        # 4. 可选深抽取（摘要过短）
        try:
            await self._maybe_extract(briefs, discarded)
        except Exception as e:
            logger.warning(f"[evidence_gather] extract 阶段异常: {e}", exc_info=True)

        # 5. 写回状态（对齐「只保留一份 briefs」：仅 prompt_vars 压缩串进终评）
        # - 不再写入 edges_var / persistence 的全量 briefs，避免 Langfuse/节点 input 三处重复
        # - 全量仅打日志摘要，需要排障时查日志或临时打开开关
        new_state = state.copy()
        prompt_vars = dict(new_state.get("prompt_vars") or {})
        prompt_briefs = _compact_briefs_for_prompt(briefs)
        prompt_discarded = _compact_discarded_for_prompt(discarded)
        briefs_json = json.dumps(prompt_briefs, ensure_ascii=False, separators=(",", ":"))
        discarded_json = json.dumps(
            prompt_discarded, ensure_ascii=False, separators=(",", ":")
        )
        prompt_vars["evidence_briefs"] = briefs_json
        prompt_vars["discarded_briefs"] = discarded_json
        prompt_vars.pop("planned_queries", None)
        # 终评模板未使用的限额字段，从 prompt_vars 去掉，减少观测噪音
        for _k in ("max_search_times", "max_bocha", "max_anysearch", "max_extract_times", "query_hint"):
            prompt_vars.pop(_k, None)
        new_state["prompt_vars"] = prompt_vars

        new_state["edges_var"] = {
            "brief_count": len(briefs),
            "prompt_brief_count": len(prompt_briefs),
            "discarded_count": len(discarded),
        }
        # 知识库开关开启时附加召回指标（开关关闭时不写，保持旧行为逐字节一致）
        if knowledge_enabled and ctx is not None:
            new_state["edges_var"]["knowledge_brief_count"] = sum(
                1 for b in briefs if b.get("tool_name") == _KNOWLEDGE_TOOL_NAME
            )
            new_state["edges_var"]["knowledge_recall_hit_rate"] = round(
                ctx.knowledge.hit_rate, 4
            )
        # 保留规划 queries 供排障，但不复制 briefs
        persistence = dict(new_state.get("persistence_edges_var") or {})
        persistence["queries"] = queries
        for _k in (
            "evidence_briefs",
            "discarded_briefs",
            "evidence_briefs_full",
            "discarded_briefs_full",
        ):
            persistence.pop(_k, None)
        new_state["persistence_edges_var"] = persistence

        # 缩短终评 HumanMessage，避免与 system 中公司/任务说明重复
        from langchain_core.messages import HumanMessage

        new_state["current_message"] = HumanMessage(
            content=(
                "请仅依据系统提示中的 company_json 与 evidence_briefs，"
                "输出带顶层键 radar_event_score 的单个 JSON 对象，不要 Markdown 围栏。"
            )
        )

        ctx = get_huayuan_radar_event_context()
        logger.info(
            f"[evidence_gather] briefs={len(briefs)} (prompt用{len(prompt_briefs)}), "
            f"discarded={len(discarded)} (prompt用{len(prompt_discarded)}), "
            f"prompt_briefs_chars={len(briefs_json)}, "
            f"bocha={getattr(ctx, 'bocha_count', None)}, "
            f"anysearch={getattr(ctx, 'anysearch_count', None)}, "
            f"knowledge_briefs="
            f"{sum(1 for b in briefs if b.get('tool_name') == _KNOWLEDGE_TOOL_NAME)}, "
            f"knowledge_enabled={knowledge_enabled}"
        )
        if briefs:
            # 仅日志保留前 3 条 URL，便于对照，不进 state
            sample_urls = [str(b.get("url") or "") for b in briefs[:3]]
            logger.info(f"[evidence_gather] sample_urls={sample_urls}")
        return new_state
