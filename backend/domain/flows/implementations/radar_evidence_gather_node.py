"""
展厅发觉：证据采集 Function 节点

按 planner 产出的 queries，节点内 asyncio.gather 并行调用博查 + AnySearch，
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
    extract_source_host,
    get_huayuan_radar_event_context,
)

logger = logging.getLogger(__name__)


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
        终评入模排序：主体命中优先，其次含动作/空间关键词，再次有 quote。

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
        compact.append(
            {
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
        )
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

        # 2. 构造并行任务：每条 query ×（博查 + AnySearch）
        tasks_meta: List[Tuple[str, str]] = []
        coros = []
        for q in queries:
            for tool_name in ("bocha_web_search", "anysearch_web_search"):
                tasks_meta.append((tool_name, q))
                coros.append(self._search_one(tool_name, q))

        results = await asyncio.gather(*coros, return_exceptions=True)

        # 3. 归一为 briefs / discarded，URL 去重
        briefs: List[Dict[str, Any]] = []
        discarded: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()

        for meta, result in zip(tasks_meta, results):
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
            f"anysearch={getattr(ctx, 'anysearch_count', None)}"
        )
        if briefs:
            # 仅日志保留前 3 条 URL，便于对照，不进 state
            sample_urls = [str(b.get("url") or "") for b in briefs[:3]]
            logger.info(f"[evidence_gather] sample_urls={sample_urls}")
        return new_state
