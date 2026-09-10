"""
华院规则二：展厅项目需求评分路由

对接 exhibition：POST /api/v1/huayuan/radar-event-score
无 Session；固定流程 huayuan_radar_event_agent；解析失败返回 500。
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

from backend.app.api.schemas.huayuan_radar_event import (
    DEFAULT_MAX_EXTRACT_TIMES,
    DEFAULT_MAX_RESULTS_PER_SEARCH,
    DEFAULT_MAX_SEARCH_TIMES,
    DEFAULT_QUERY_HINT,
    VALID_EVIDENCE_SCORES,
    VALID_SPECIFICITY_SCORES,
    HuayuanRadarEventRequest,
    HuayuanRadarEventResponse,
    RadarEventDiscardedItem,
    RadarEventEvidenceItem,
    RadarEventScoreResult,
)
from backend.domain.flows.manager import FlowManager
from backend.domain.state import FlowState
from backend.domain.tools.huayuan_radar_event_context import (
    HuayuanRadarEventContext,
    build_radar_event_context_from_request,
    classify_authority_tier,
    extract_source_host,
)
from backend.infrastructure.observability.langfuse_handler import create_langfuse_handler

logger = logging.getLogger(__name__)
router = APIRouter()

HUAYUAN_RADAR_EVENT_FLOW_KEY = "huayuan_radar_event_agent"
VALID_SUBJECT_CONFIDENCE = {"high", "medium", "low", "unknown"}
VALID_FACT_STATUS = {"confirmed", "inferred", "unknown", "conflict"}
VALID_ADMISSION_HINT = {"pass", "reject_unrelated", "pending_verify", "expired"}
DEFAULT_MAX_EXTRACT_CHARS = 12000


def _dumps_prompt_var(value: Any) -> str:
    """将对象序列化为提示词占位符字符串。"""
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def build_radar_event_initial_state(
    request: HuayuanRadarEventRequest,
    trace_id: str,
) -> FlowState:
    """
        构造规则二流程初始状态。

        Args:
            request: 评分请求
            trace_id: Trace ID

        Returns:
            FlowState
    """
    ctx = request.context
    query_hint = (ctx.query_hint or "").strip() or DEFAULT_QUERY_HINT
    return {
        "current_message": HumanMessage(
            content=(
                f"{request.query}\n\n"
                "请严格输出规定的单个 JSON 对象（含 exhibition_related、分项分与 evidences），"
                "不要使用 Markdown 代码围栏。"
            )
        ),
        "history_messages": [],
        "flow_msgs": [],
        "session_id": "",
        "token_id": "",
        "trace_id": trace_id,
        "prompt_vars": {
            "current_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "company_json": _dumps_prompt_var(ctx.company.model_dump()),
            "time_from": ctx.time_from or "",
            "time_to": ctx.time_to or "",
            "query_hint": query_hint,
            "max_search_times": str(
                ctx.max_search_times
                if ctx.max_search_times is not None
                else DEFAULT_MAX_SEARCH_TIMES
            ),
            "max_extract_times": str(
                ctx.max_extract_times
                if ctx.max_extract_times is not None
                else DEFAULT_MAX_EXTRACT_TIMES
            ),
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
    """
        从模型输出中解析 JSON 对象。

        Args:
            text: 原始输出

        Returns:
            dict 或 None
    """
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


def _as_bool(value: Any, default: bool = False) -> bool:
    """宽松布尔解析。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in {"true", "1", "yes", "y"}:
        return True
    if s in {"false", "0", "no", "n"}:
        return False
    return default


def _normalize_subject_confidence(value: Any) -> str:
    """规范化主体置信。"""
    s = str(value or "").strip().lower()
    return s if s in VALID_SUBJECT_CONFIDENCE else "unknown"


def _normalize_fact_status(value: Any) -> str:
    """规范化事实状态。"""
    s = str(value or "").strip().lower()
    if s == "conflicted":
        s = "conflict"
    return s if s in VALID_FACT_STATUS else "unknown"


def _normalize_admission_hint(value: Any) -> str:
    """规范化准入提示。"""
    s = str(value or "").strip().lower()
    return s if s in VALID_ADMISSION_HINT else "pending_verify"


def _parse_optional_score(value: Any, allowed: set[int], field_name: str) -> Optional[int]:
    """
        解析离散合法分值；非法则抛 ValueError。

        Args:
            value: 原始分值
            allowed: 合法集合
            field_name: 字段名（用于错误信息）

        Returns:
            int 或 None

        Raises:
            ValueError: 分值非法
    """
    if value is None or value == "":
        return None
    try:
        score = int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field_name} 非法: {value}") from e
    if score not in allowed:
        raise ValueError(
            f"{field_name}={score} 不在合法档位 {sorted(allowed)} 内"
        )
    return score


def _parse_evidences(raw: Any) -> List[RadarEventEvidenceItem]:
    """解析 evidences 列表。"""
    if not isinstance(raw, list):
        return []
    items: List[RadarEventEvidenceItem] = []
    for ev in raw:
        if not isinstance(ev, dict):
            continue
        url = ev.get("url") or ev.get("source_url") or ev.get("sourceUrl")
        url_str = str(url).strip() if url else None
        host = ev.get("source_host") or ev.get("sourceHost")
        if not host and url_str:
            host = extract_source_host(url_str)
        tier = ev.get("authority_tier") or ev.get("authorityTier")
        if not tier and url_str:
            tier = classify_authority_tier(url_str)
        items.append(
            RadarEventEvidenceItem(
                title=ev.get("title"),
                summary=ev.get("summary"),
                quote=ev.get("quote"),
                url=url_str,
                publish_date=ev.get("publish_date") or ev.get("publishDate"),
                source_host=str(host) if host else None,
                authority_tier=str(tier) if tier else None,
                kept=_as_bool(ev.get("kept", True), True),
            )
        )
    return items


def _parse_discarded(raw: Any) -> List[RadarEventDiscardedItem]:
    """解析 discarded 列表。"""
    if not isinstance(raw, list):
        return []
    items: List[RadarEventDiscardedItem] = []
    for d in raw:
        if not isinstance(d, dict):
            continue
        items.append(
            RadarEventDiscardedItem(
                title=d.get("title"),
                url=d.get("url"),
                reason=d.get("reason"),
            )
        )
    return items


def parse_radar_event_score_from_ai_text(text: str) -> RadarEventScoreResult:
    """
        解析模型输出为 RadarEventScoreResult；失败抛 ValueError（由路由转 500）。

        Args:
            text: 模型最终文本

        Returns:
            RadarEventScoreResult

        Raises:
            ValueError: 无法解析 JSON、缺关键字段或分值非法
    """
    # 1. 解析 JSON
    obj = _extract_json_object(text)
    if not obj:
        raise ValueError("无法从模型输出中解析 JSON 对象")

    if "exhibition_related" not in obj and isinstance(obj.get("radar_event_score"), dict):
        obj = obj["radar_event_score"]

    if "exhibition_related" not in obj:
        raise ValueError("JSON 中缺少 exhibition_related 字段")

    # 2. 解析分值（非法直接失败，对齐设计 Q4）
    evidence_score = _parse_optional_score(
        obj.get("evidence_score", obj.get("evidenceScore")),
        VALID_EVIDENCE_SCORES,
        "evidence_score",
    )
    specificity_score = _parse_optional_score(
        obj.get("specificity_score", obj.get("specificityScore")),
        VALID_SPECIFICITY_SCORES,
        "specificity_score",
    )

    exhibition_related = _as_bool(obj.get("exhibition_related"), False)
    expired_or_done = _as_bool(
        obj.get("expired_or_done", obj.get("expiredOrDone")), False
    )
    evidences = _parse_evidences(obj.get("evidences") or obj.get("evidence") or [])

    # 3. 准入/失效时清空分数；有分必须有证据 URL
    total_score: Optional[int]
    if not exhibition_related or expired_or_done:
        evidence_score = None
        specificity_score = None
        total_score = None
    else:
        if evidence_score is None and specificity_score is None:
            total_score = None
        else:
            # 缺一维时按 0 参与合计（调用方可再校验）
            total_score = int(evidence_score or 0) + int(specificity_score or 0)
            raw_total = obj.get("total_score", obj.get("totalScore"))
            if raw_total is not None and raw_total != "":
                try:
                    model_total = int(raw_total)
                    if model_total != total_score:
                        logger.warning(
                            f"模型 total_score={model_total} 与两维之和 {total_score} 不一致，已以重算为准"
                        )
                except (TypeError, ValueError):
                    pass
            kept_with_url = [
                e for e in evidences if e.kept and e.url and e.url.startswith("http")
            ]
            if total_score is not None and total_score > 0 and not kept_with_url:
                raise ValueError("有分必有据：total_score>0 时 evidences 须含可访问 URL")

    tags_raw = obj.get("tags") or []
    tags = [str(t).strip() for t in tags_raw if str(t).strip()] if isinstance(tags_raw, list) else []

    admission_hint = _normalize_admission_hint(
        obj.get("admission_hint") or obj.get("admissionHint")
    )
    if not exhibition_related:
        admission_hint = "reject_unrelated"
    elif expired_or_done:
        admission_hint = "expired"

    return RadarEventScoreResult(
        exhibition_related=exhibition_related,
        subject_confidence=_normalize_subject_confidence(
            obj.get("subject_confidence") or obj.get("subjectConfidence")
        ),
        space_object=obj.get("space_object") or obj.get("spaceObject"),
        action=obj.get("action"),
        place=obj.get("place"),
        time_text=obj.get("time_text") or obj.get("timeText"),
        evidence_score=evidence_score,
        specificity_score=specificity_score,
        total_score=total_score,
        tags=tags,
        expired_or_done=expired_or_done,
        fact_status=_normalize_fact_status(
            obj.get("fact_status") or obj.get("factStatus")
        ),
        admission_hint=admission_hint,
        score_reason=obj.get("score_reason") or obj.get("scoreReason"),
        evidences=evidences,
        discarded=_parse_discarded(obj.get("discarded") or []),
        search_count=int(obj.get("search_count") or obj.get("searchCount") or 0),
        extract_count=int(obj.get("extract_count") or obj.get("extractCount") or 0),
    )


@router.post("/huayuan/radar-event-score", response_model=HuayuanRadarEventResponse)
async def huayuan_radar_event_score(
    request: HuayuanRadarEventRequest,
) -> HuayuanRadarEventResponse:
    """
        华院规则二评分接口：ReAct + AnySearch，返回两维分与证据链。

        Args:
            request: 评分请求（query + context.company）

        Returns:
            含 trace_id 与 radar_event_score 的响应

        Raises:
            HTTPException: 流程失败或解析失败时 500
    """
    # 1. trace_id 与运行参数
    trace_id = request.trace_id or secrets.token_hex(16)
    ctx_body = request.context
    company = ctx_body.company
    max_search_times = (
        ctx_body.max_search_times
        if ctx_body.max_search_times is not None
        else DEFAULT_MAX_SEARCH_TIMES
    )
    max_extract_times = (
        ctx_body.max_extract_times
        if ctx_body.max_extract_times is not None
        else DEFAULT_MAX_EXTRACT_TIMES
    )
    max_results = (
        ctx_body.max_results_per_search
        if ctx_body.max_results_per_search is not None
        else DEFAULT_MAX_RESULTS_PER_SEARCH
    )

    logger.info(
        f"[华院RadarEvent请求开始] trace_id={trace_id}, "
        f"company={company.company_name}, stock_code={company.stock_code}, "
        f"event_job_id={ctx_body.event_job_id}, max_search_times={max_search_times}"
    )

    runtime_ctx = build_radar_event_context_from_request(
        company_name=company.company_name,
        stock_code=company.stock_code or "",
        aliases=company.aliases,
        max_search_times=max_search_times,
        max_extract_times=max_extract_times,
        max_results_per_search=max_results,
        max_extract_chars=DEFAULT_MAX_EXTRACT_CHARS,
        event_job_id=ctx_body.event_job_id,
        trace_id=trace_id,
    )

    try:
        # 2. 加载流程并执行
        graph = FlowManager.get_flow(HUAYUAN_RADAR_EVENT_FLOW_KEY)
        initial_state = build_radar_event_initial_state(request, trace_id)
        langfuse_handler = create_langfuse_handler(context={"trace_id": trace_id})

        config: Dict[str, Any] = {
            "configurable": {"thread_id": f"huayuan_radar_event_{trace_id}"},
        }
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]
            config["metadata"] = {
                "langfuse_tags": ["huayuan_radar_event", "api"],
                "flow_key": HUAYUAN_RADAR_EVENT_FLOW_KEY,
                "source": "huayuan_radar_event_api",
                "event_job_id": str(ctx_body.event_job_id or ""),
            }

        with HuayuanRadarEventContext(runtime_ctx):
            result = await graph.ainvoke(initial_state, config)

        # 3. 解析评分结果（失败 → 500）
        ai_text = extract_last_ai_text(result)
        if not ai_text:
            raise ValueError("流程未返回 AI 消息")

        score_result = parse_radar_event_score_from_ai_text(ai_text)

        # 用运行时真实计数回填（若模型漏写）
        if score_result.search_count <= 0 and runtime_ctx.search_count > 0:
            score_result.search_count = runtime_ctx.search_count
        if score_result.extract_count <= 0 and runtime_ctx.extract_count > 0:
            score_result.extract_count = runtime_ctx.extract_count

        response_json = score_result.model_dump_json()
        logger.info(
            f"[华院RadarEvent请求完成] trace_id={trace_id}, "
            f"exhibition_related={score_result.exhibition_related}, "
            f"total_score={score_result.total_score}, "
            f"search_count={score_result.search_count}"
        )
        return HuayuanRadarEventResponse(
            trace_id=trace_id,
            radar_event_score=score_result,
            response=response_json,
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"华院RadarEvent处理失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"radar_event_score 解析或处理失败: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(f"华院RadarEvent请求异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}") from e
