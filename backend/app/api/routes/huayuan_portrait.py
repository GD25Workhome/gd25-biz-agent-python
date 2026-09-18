"""
华院五维画像评分路由

对接 exhibition：POST /api/v1/huayuan/portrait
"""
from __future__ import annotations

import json
import logging
import re
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage, HumanMessage

from backend.app.api.schemas.huayuan_portrait import (
    REQUIRED_DIM_CODES,
    HuayuanPortraitRequest,
    HuayuanPortraitResponse,
    PortraitCitation,
    PortraitResult,
    PortraitScoreItem,
)
from backend.domain.flows.manager import FlowManager
from backend.domain.state import FlowState
from backend.domain.tools.huayuan_portrait_context import (
    HuayuanPortraitContext,
    build_portrait_context_from_request,
    get_huayuan_portrait_context,
    resolve_portrait_knowledge_config,
)

from backend.infrastructure.observability.langfuse_handler import create_langfuse_handler

logger = logging.getLogger(__name__)
router = APIRouter()

HUAYUAN_PORTRAIT_FLOW_KEY = "huayuan_portrait_agent"
DEFAULT_MAX_LOAD_TIMES = 3
DEFAULT_MAX_CHARS = 12000
VALID_TIERS = {"strong", "stronger", "medium", "weak_or_unknown"}
VALID_FACT_STATUS = {"confirmed", "inferred", "unknown"}


def _dumps_prompt_var(value: Any) -> str:
    """将对象序列化为提示词占位符字符串。"""
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _coerce_candidate_docs(ctx_body: Any) -> List[Dict[str, Any]]:
    """合并 candidate_docs 与遗留 file_ids。"""
    out: List[Dict[str, Any]] = []
    for item in getattr(ctx_body, "candidate_docs", None) or []:
        if hasattr(item, "model_dump"):
            out.append(item.model_dump())
        elif isinstance(item, dict):
            out.append(dict(item))
    if out:
        return out
    for fid in getattr(ctx_body, "file_ids", None) or []:
        s = str(fid).strip()
        if s:
            out.append({"doc_id": s, "content_grade": "full"})
    return out


def build_portrait_initial_state(request: HuayuanPortraitRequest, trace_id: str) -> FlowState:
    """
        构造画像流程初始状态。

        Args:
            request: 画像请求
            trace_id: Trace ID

        Returns:
            FlowState
    """
    ctx = request.context
    knowledge = resolve_portrait_knowledge_config(ctx)
    max_load = (
        ctx.max_load_times
        if ctx.max_load_times is not None
        else knowledge.get("max_load_times", DEFAULT_MAX_LOAD_TIMES)
    )
    return {
        "current_message": HumanMessage(
            content=(
                f"{request.query}\n\n"
                "请严格输出规定的单个 JSON 对象（含全部五维 score_items），不要使用 Markdown 代码围栏。"
            )
        ),
        "history_messages": [],
        "flow_msgs": [],
        "session_id": "",
        "token_id": "",
        "trace_id": trace_id,
        "prompt_vars": {
            "current_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "company_json": _dumps_prompt_var(ctx.company),
            "rule_prefill_json": _dumps_prompt_var(ctx.rule_prefill),
            "candidate_docs_json": _dumps_prompt_var(_coerce_candidate_docs(ctx)),
            "knowledge_briefs_json": "[]",
            "knowledge_recall_hint": "",
            "rule_version": ctx.rule_version or "",
            "max_load_times": str(max_load),
        },
    }


def extract_last_ai_text(result: Dict[str, Any]) -> str:
    """从流程结果中取最后一条 AI 文本。"""
    flow_msgs = result.get("flow_msgs", []) or []
    ai_messages = [msg for msg in flow_msgs if isinstance(msg, AIMessage)]
    if not ai_messages:
        return ""
    raw = ai_messages[-1].content if hasattr(ai_messages[-1], "content") else str(ai_messages[-1])
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    return str(raw or "").strip()


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出中解析 JSON 对象。"""
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
        s = s.strip()
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str) and parsed.strip().startswith("{"):
            again = json.loads(parsed)
            if isinstance(again, dict):
                return again
    except (json.JSONDecodeError, TypeError):
        pass

    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(s)):
        c = s[i]
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                chunk = s[start : i + 1]
                try:
                    obj = json.loads(chunk)
                    if isinstance(obj, dict):
                        return obj
                except (json.JSONDecodeError, TypeError):
                    return None
    return None


def _normalize_tier(tier: Any) -> str:
    """规范化档位；非法则降为 weak_or_unknown。"""
    t = str(tier or "").strip().lower()
    return t if t in VALID_TIERS else "weak_or_unknown"


def _normalize_fact_status(status: Any) -> str:
    """规范化证据状态（画像不含 conflict）。"""
    s = str(status or "").strip().lower()
    if s == "conflict" or s == "conflicted":
        s = "inferred"
    return s if s in VALID_FACT_STATUS else "unknown"


def _prefill_tier_for_code(rule_prefill: Optional[Dict[str, Any]], code: str) -> Optional[str]:
    """从 rule_prefill 读取某维 tier。"""
    if not isinstance(rule_prefill, dict):
        return None
    item = rule_prefill.get(code)
    if isinstance(item, dict) and item.get("tier"):
        return _normalize_tier(item.get("tier"))
    return None


def _parse_citations(raw: Any) -> List[PortraitCitation]:
    """解析 citations 数组。"""
    if not isinstance(raw, list):
        return []
    out: List[PortraitCitation] = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        st = str(c.get("source_type") or c.get("sourceType") or "").strip().lower()
        if not st:
            if c.get("doc_id") or c.get("docId"):
                st = "knowledge_base"
            else:
                st = "web"
        out.append(
            PortraitCitation(
                source_type=st,
                doc_id=c.get("doc_id", c.get("docId")),
                title=c.get("title"),
                url=c.get("url"),
                source_kind=c.get("source_kind") or c.get("sourceKind"),
                content_grade=c.get("content_grade") or c.get("contentGrade"),
                quote=c.get("quote"),
                cite_reason=c.get("cite_reason") or c.get("citeReason"),
            )
        )
    return out


def _soft_filter_citations(
    citations: List[PortraitCitation],
    loaded_content: Dict[str, str],
) -> List[PortraitCitation]:
    """
        软校验：quote 须为已加载截断正文的子串；KB 正式引用须 full。

        Args:
            citations: 原始引用
            loaded_content: doc_id -> 截断正文

        Returns:
            过滤后的 citations
    """
    kept: List[PortraitCitation] = []
    for c in citations:
        if c.source_type == "knowledge_base":
            grade = str(c.content_grade or "").lower()
            if grade and grade != "full":
                continue
        quote = str(c.quote or "").strip()
        doc_key = str(c.doc_id or "").strip()
        if quote and doc_key and doc_key in loaded_content:
            base = loaded_content[doc_key]
            if quote not in base:
                continue
        elif quote and c.source_type == "knowledge_base" and doc_key in loaded_content:
            continue
        kept.append(c)
    return kept


def ensure_all_score_items(
    portrait: PortraitResult,
    rule_prefill: Optional[Dict[str, Any]],
) -> PortraitResult:
    """确保五维 score_items 齐全。"""
    by_code: Dict[str, PortraitScoreItem] = {}
    for item in portrait.score_items:
        code = str(item.code).strip()
        if code in REQUIRED_DIM_CODES and code not in by_code:
            by_code[code] = item

    filled: List[PortraitScoreItem] = []
    for code in REQUIRED_DIM_CODES:
        if code in by_code:
            filled.append(by_code[code])
            continue
        prefill_tier = _prefill_tier_for_code(rule_prefill, code)
        if prefill_tier:
            filled.append(
                PortraitScoreItem(
                    code=code,
                    tier=prefill_tier,
                    fact_status="confirmed",
                    score_reason="规则预填档位，模型未返回该维",
                    citations=[],
                )
            )
        else:
            filled.append(
                PortraitScoreItem(
                    code=code,
                    tier="weak_or_unknown",
                    fact_status="unknown",
                    score_reason="模型未返回该维，已按无依据弱档补齐",
                    citations=[],
                    missing_reason="模型未返回该维",
                )
            )
    portrait.score_items = filled
    return portrait


def parse_portrait_from_ai_text(
    text: str,
    rule_prefill: Optional[Dict[str, Any]],
    *,
    loaded_content: Optional[Dict[str, str]] = None,
) -> PortraitResult:
    """
        解析模型输出为 PortraitResult；失败抛 ValueError。

        Args:
            text: 模型最终文本
            rule_prefill: 用于补齐缺失维
            loaded_content: load 工具缓存的正文（quote 软校验）

        Returns:
            PortraitResult
    """
    obj = _extract_json_object(text)
    if not obj:
        raise ValueError("无法从模型输出中解析 JSON 对象")

    if "score_items" not in obj and isinstance(obj.get("portrait"), dict):
        obj = obj["portrait"]

    raw_items = obj.get("score_items")
    if raw_items is None and obj.get("dimensions"):
        raise ValueError("请使用 score_items 结构，dimensions 已废弃")

    if not isinstance(raw_items, list):
        raise ValueError("score_items 必须是数组")

    content_map = dict(loaded_content or {})
    score_items: List[PortraitScoreItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        reason = str(item.get("score_reason") or item.get("scoreReason") or "").strip()
        if len(reason) < 8:
            reason = (reason + "；依据不足已保守定档。")[:200]
        citations = _soft_filter_citations(
            _parse_citations(item.get("citations") or []),
            content_map,
        )
        tier = _normalize_tier(item.get("tier"))
        prefill_tier = _prefill_tier_for_code(rule_prefill, code)
        if not citations and not prefill_tier and tier in ("strong", "stronger"):
            tier = "medium" if tier == "stronger" else "weak_or_unknown"
            if "弱档" not in reason:
                reason = f"{reason}（引用未通过校验，已降档）"

        score_items.append(
            PortraitScoreItem(
                code=code,
                tier=tier,
                fact_status=_normalize_fact_status(
                    item.get("fact_status") or item.get("factStatus")
                ),
                score_reason=reason,
                citations=citations,
                missing_reason=item.get("missing_reason") or item.get("missingReason"),
            )
        )

    portrait = PortraitResult(
        score_items=score_items,
        loaded_doc_ids=[str(x) for x in (obj.get("loaded_doc_ids") or obj.get("loadedDocIds") or [])],
        discarded_doc_ids=[
            str(x) for x in (obj.get("discarded_doc_ids") or obj.get("discardedDocIds") or [])
        ],
        load_count=int(obj.get("load_count") or obj.get("loadCount") or 0),
        kb_hit_count=int(obj.get("kb_hit_count") or obj.get("kbHitCount") or 0),
        kb_load_count=int(obj.get("kb_load_count") or obj.get("kbLoadCount") or 0),
    )
    return ensure_all_score_items(portrait, rule_prefill)


def _company_id_from_context(ctx_body: Any) -> Optional[int]:
    """从 context.company 解析 company_id。"""
    company = getattr(ctx_body, "company", None) or {}
    if hasattr(company, "get"):
        raw = company.get("company_id", company.get("companyId"))
    else:
        raw = getattr(company, "company_id", None)
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return None


@router.post("/huayuan/portrait", response_model=HuayuanPortraitResponse)
async def huayuan_portrait(request: HuayuanPortraitRequest) -> HuayuanPortraitResponse:
    """
        华院五维画像评分：gather + ReAct 终评。

        Args:
            request: 画像请求

        Returns:
            含 trace_id 与 portrait 的响应
    """
    trace_id = request.trace_id or secrets.token_hex(16)
    ctx_body = request.context
    knowledge = resolve_portrait_knowledge_config(ctx_body)
    max_load_times = (
        ctx_body.max_load_times
        if ctx_body.max_load_times is not None
        else int(knowledge.get("max_load_times", DEFAULT_MAX_LOAD_TIMES))
    )
    company_id = _company_id_from_context(ctx_body)

    logger.info(
        f"[华院Portrait请求开始] trace_id={trace_id}, "
        f"knowledge_enabled={knowledge['enabled']}, max_load_times={max_load_times}, "
        f"profile_job_id={ctx_body.profile_job_id}"
    )

    portrait_ctx = build_portrait_context_from_request(
        company_id=company_id,
        allowed_doc_ids=[],
        max_load_times=max_load_times,
        max_chars=DEFAULT_MAX_CHARS,
        max_docs=int(knowledge.get("max_docs", 20)),
        knowledge_enabled=bool(knowledge.get("enabled", True)),
        prefer_source_kinds=knowledge.get("prefer_source_kinds"),
        profile_job_id=ctx_body.profile_job_id,
        trace_id=trace_id,
    )

    try:
        graph = FlowManager.get_flow(HUAYUAN_PORTRAIT_FLOW_KEY)
        initial_state = build_portrait_initial_state(request, trace_id)
        langfuse_handler = create_langfuse_handler(context={"trace_id": trace_id})

        config: Dict[str, Any] = {
            "configurable": {"thread_id": f"huayuan_portrait_{trace_id}"},
        }
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]
            config["metadata"] = {
                "langfuse_tags": ["huayuan_portrait", "api", "pipeline_v2"],
                "flow_key": HUAYUAN_PORTRAIT_FLOW_KEY,
                "source": "huayuan_portrait_api",
                "profile_job_id": str(ctx_body.profile_job_id or ""),
            }

        with HuayuanPortraitContext(portrait_ctx):
            result = await graph.ainvoke(initial_state, config)

        ai_text = extract_last_ai_text(result)
        if not ai_text:
            raise ValueError("流程未返回 AI 消息")

        runtime = get_huayuan_portrait_context() or portrait_ctx
        portrait = parse_portrait_from_ai_text(
            ai_text,
            ctx_body.rule_prefill,
            loaded_content=dict(runtime.loaded_content_by_doc),
        )

        if not portrait.loaded_doc_ids and runtime.loaded_doc_ids:
            portrait.loaded_doc_ids = sorted(runtime.loaded_doc_ids)
        if portrait.load_count <= 0 and runtime.load_count > 0:
            portrait.load_count = runtime.load_count
        if portrait.kb_load_count <= 0 and runtime.load_count > 0:
            portrait.kb_load_count = runtime.load_count

        response_json = portrait.model_dump_json()
        logger.info(
            f"[华院Portrait请求完成] trace_id={trace_id}, "
            f"items={len(portrait.score_items)}, load_count={portrait.load_count}, "
            f"whitelist={len(runtime.allowed_doc_ids)}"
        )
        return HuayuanPortraitResponse(
            trace_id=trace_id,
            portrait=portrait,
            response=response_json,
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"华院Portrait处理失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"portrait 解析或处理失败: {str(e)}") from e
    except Exception as e:
        logger.error(f"华院Portrait请求异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}") from e
