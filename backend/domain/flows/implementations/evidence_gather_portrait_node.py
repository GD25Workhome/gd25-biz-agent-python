"""
五维画像：证据采集 Function 节点（Milvus 召回 + candidate_docs 补漏）。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set

from langchain_core.messages import HumanMessage

from backend.app.config import settings
from backend.domain.flows.implementations.radar_evidence_gather_node import (
    _clip,
    _KNOWLEDGE_TOOL_NAME,
)
from backend.domain.flows.nodes.base_function import BaseFunctionNode
from backend.domain.knowledge.radar_kb_recall import recall_doc_briefs_for_queries
from backend.domain.state import FlowState
from backend.domain.tools.huayuan_portrait_context import get_huayuan_portrait_context

logger = logging.getLogger(__name__)

_PORTRAIT_QUERY_TEMPLATES = (
    '{name} 展厅 数字化 展示',
    '{name} 业务 复杂度 产品',
    '{name} 智能化 数字转型',
    '{name} 品牌 标杆 行业',
    '{name} 预算 投入 建设',
)


def _company_from_state(state: FlowState) -> tuple[Optional[int], str]:
    """从 prompt_vars.company_json 解析 company_id 与 company_name。"""
    prompt_vars = state.get("prompt_vars") or {}
    company_json = prompt_vars.get("company_json") or ""
    company_id: Optional[int] = None
    company_name = ""
    if isinstance(company_json, str) and company_json.strip().startswith("{"):
        try:
            obj = json.loads(company_json)
            if isinstance(obj, dict):
                company_name = str(obj.get("company_name") or obj.get("companyName") or "")
                raw_id = obj.get("company_id", obj.get("companyId"))
                if raw_id is not None and str(raw_id).strip().lstrip("-").isdigit():
                    company_id = int(raw_id)
        except Exception:
            pass
    ctx = get_huayuan_portrait_context()
    if ctx is not None:
        if ctx.company_id is not None:
            company_id = ctx.company_id
    return company_id, company_name


def _build_portrait_queries(company_name: str) -> List[str]:
    """构造画像召回 query 列表。"""
    name = (company_name or "").strip() or "目标公司"
    quoted = f'"{name}"'
    out: List[str] = []
    seen: Set[str] = set()
    for tpl in _PORTRAIT_QUERY_TEMPLATES:
        q = tpl.format(name=quoted)
        if q in seen:
            continue
        seen.add(q)
        out.append(q)
    return out[:5]


def _merge_candidate_docs(
    recalled: List[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    *,
    max_docs: int,
) -> List[Dict[str, Any]]:
    """
        召回为主；条数不足 max_docs 时按 candidate_docs 补漏（doc_id 去重）。

        Args:
            recalled: Milvus 召回 brief
            candidates: Java 传入的 candidate_docs
            max_docs: 最终上限

        Returns:
            合并后的 brief 列表
    """
    merged: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for b in recalled:
        doc_id = str(b.get("doc_id") or "").strip()
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        merged.append(dict(b))
        if len(merged) >= max_docs:
            return merged

    if len(merged) >= max_docs:
        return merged

    for c in candidates:
        if not isinstance(c, dict):
            continue
        doc_id = str(c.get("doc_id") or c.get("docId") or "").strip()
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        merged.append(
            {
                "doc_id": doc_id,
                "title": c.get("title"),
                "url": str(c.get("url") or "").strip(),
                "quote": _clip(str(c.get("summary") or c.get("quote") or ""), 200) or None,
                "content_grade": c.get("content_grade") or c.get("contentGrade") or "full",
                "source_kind": c.get("source_kind") or c.get("sourceKind"),
                "score": c.get("score"),
            }
        )
        if len(merged) >= max_docs:
            break
    return merged


def _briefs_for_prompt(briefs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """压缩写入终评 prompt 的 knowledge briefs。"""
    quote_limit = int(settings.KNOWLEDGE_BRIEF_QUOTE_MAX_CHARS)
    out: List[Dict[str, Any]] = []
    for b in briefs:
        grade = str(b.get("content_grade") or "").lower()
        item = {
            "doc_id": str(b.get("doc_id") or ""),
            "title": b.get("title"),
            "url": b.get("url"),
            "quote": _clip(str(b.get("quote") or ""), quote_limit) or None,
            "content_grade": b.get("content_grade"),
            "source_kind": b.get("source_kind"),
            "score": b.get("score"),
            "tool_name": _KNOWLEDGE_TOOL_NAME,
            "title_only": grade == "stub",
        }
        out.append(item)
    return out


class EvidenceGatherPortraitNode(BaseFunctionNode):
    """画像 gather：Milvus 召回 + candidate 补漏 → 白名单 + prompt briefs。"""

    @classmethod
    def get_key(cls) -> str:
        """Function 注册 key。"""
        return "evidence_gather_portrait_func"

    async def execute(self, state: FlowState) -> FlowState:
        """
            执行召回与补漏，写入 prompt_vars.knowledge_briefs_json。

            Args:
                state: 流程状态

            Returns:
                更新后的状态
        """
        ctx = get_huayuan_portrait_context()
        company_id, company_name = _company_from_state(state)
        max_docs = int(getattr(ctx, "max_docs", 20) or 20) if ctx else 20

        candidate_docs: List[Dict[str, Any]] = []
        prompt_vars = dict(state.get("prompt_vars") or {})
        raw_candidates = prompt_vars.get("candidate_docs_json") or "[]"
        if isinstance(raw_candidates, str):
            try:
                parsed = json.loads(raw_candidates)
                if isinstance(parsed, list):
                    candidate_docs = [x for x in parsed if isinstance(x, dict)]
            except Exception:
                candidate_docs = []

        recalled: List[Dict[str, Any]] = []
        recall_error = ""
        if ctx is not None and ctx.knowledge_enabled and company_id is not None:
            queries = _build_portrait_queries(company_name)
            source_kind = None
            if ctx.prefer_source_kinds:
                source_kind = ctx.prefer_source_kinds[0]
            factor = max(1, int(settings.KNOWLEDGE_SEARCH_CHUNK_TOP_K_FACTOR))
            top_k = min(128, max(max_docs * factor, max_docs + 8))
            recalled, payloads = await recall_doc_briefs_for_queries(
                queries,
                company_id=int(company_id),
                top_k_per_query=top_k,
                source_kind=source_kind,
            )
            if payloads and all(not p.get("ok") for p in payloads if isinstance(p, dict)):
                recall_error = str((payloads[0] or {}).get("error") or "知识库检索失败")
        elif ctx is not None and ctx.knowledge_enabled and company_id is None:
            recall_error = "缺少 company_id，已跳过 Milvus 召回"

        merged = _merge_candidate_docs(recalled, candidate_docs, max_docs=max_docs)
        whitelist_ids = [str(b.get("doc_id") or "").strip() for b in merged if b.get("doc_id")]

        if ctx is not None:
            ctx.allowed_doc_ids.clear()
            ctx.register_allowed(whitelist_ids)

        prompt_briefs = _briefs_for_prompt(merged)
        briefs_json = json.dumps(prompt_briefs, ensure_ascii=False, separators=(",", ":"))

        new_state = state.copy()
        new_prompt = dict(prompt_vars)
        new_prompt["knowledge_briefs_json"] = briefs_json
        if recall_error and not merged:
            new_prompt["knowledge_recall_hint"] = (
                "该公司知识库召回为空，请结合 rule_prefill 与可得线索给出弱档并说明原因。"
            )
        elif recall_error:
            new_prompt["knowledge_recall_hint"] = f"知识库部分 query 失败：{recall_error[:120]}"
        else:
            new_prompt.pop("knowledge_recall_hint", None)
        new_state["prompt_vars"] = new_prompt
        new_state["edges_var"] = {
            "knowledge_brief_count": len(merged),
            "knowledge_whitelist_size": len(whitelist_ids),
        }
        new_state["current_message"] = HumanMessage(
            content=(
                "请依据系统提示中的 company_json、rule_prefill 与 knowledge_briefs，"
                "输出含 score_items 的单个 JSON 对象，不要使用 Markdown 围栏。"
            )
        )
        logger.info(
            "[portrait_gather] company=%s recalled=%s merged=%s whitelist=%s",
            company_name,
            len(recalled),
            len(merged),
            len(whitelist_ids),
        )
        return new_state
