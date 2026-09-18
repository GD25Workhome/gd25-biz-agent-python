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
    RadarEventScoreItem,
    DEFAULT_KNOWLEDGE_MAX_CHARS,
    DEFAULT_KNOWLEDGE_MAX_DOCS,
    DEFAULT_KNOWLEDGE_MAX_LOAD_TIMES,
    DEFAULT_MAX_ANYSEARCH,
    DEFAULT_MAX_BOCHA,
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
    MAX_KNOWLEDGE_DOCS_LIMIT,
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


def resolve_radar_tool_quotas(
    ctx_body: Any,
) -> tuple[int, int, int, int]:
    """
        解析分工具搜索/抽取配额。

        优先 max_bocha / max_anysearch；若未传则回退 max_search_times（两工具各自使用该值）；
        再回退默认常量。

        Args:
            ctx_body: 请求 context

        Returns:
            (max_bocha, max_anysearch, max_extract_times, max_results_per_search)
    """
    legacy = (
        ctx_body.max_search_times
        if ctx_body.max_search_times is not None
        else None
    )
    max_bocha = (
        ctx_body.max_bocha
        if getattr(ctx_body, "max_bocha", None) is not None
        else (legacy if legacy is not None else DEFAULT_MAX_BOCHA)
    )
    max_anysearch = (
        ctx_body.max_anysearch
        if getattr(ctx_body, "max_anysearch", None) is not None
        else (legacy if legacy is not None else DEFAULT_MAX_ANYSEARCH)
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
    return int(max_bocha), int(max_anysearch), int(max_extract_times), int(max_results)


def resolve_radar_knowledge_config(ctx_body: Any) -> Dict[str, Any]:
    """
        解析知识库开关与限额（请求可选 `context.knowledge`）。

        缺省或未传 knowledge 时 **enabled=true**（外网仍必跑，KB 默认增强）。
        显式 `enabled=false` 时关闭 Milvus 召回。

        Args:
            ctx_body: 请求 context

        Returns:
            {"enabled": bool, "max_docs": int, "max_load_times": int}
    """
    cfg = getattr(ctx_body, "knowledge", None)
    if cfg is None:
        return {
            "enabled": True,
            "max_docs": DEFAULT_KNOWLEDGE_MAX_DOCS,
            "max_load_times": DEFAULT_KNOWLEDGE_MAX_LOAD_TIMES,
        }
    enabled = getattr(cfg, "enabled", True)
    if not bool(enabled):
        return {
            "enabled": False,
            "max_docs": DEFAULT_KNOWLEDGE_MAX_DOCS,
            "max_load_times": DEFAULT_KNOWLEDGE_MAX_LOAD_TIMES,
        }

    raw_docs = getattr(cfg, "max_docs", None)
    raw_loads = getattr(cfg, "max_load_times", None)
    max_docs = int(raw_docs) if raw_docs is not None else DEFAULT_KNOWLEDGE_MAX_DOCS
    max_load_times = (
        int(raw_loads) if raw_loads is not None else DEFAULT_KNOWLEDGE_MAX_LOAD_TIMES
    )
    return {
        "enabled": True,
        "max_docs": max(1, min(MAX_KNOWLEDGE_DOCS_LIMIT, max_docs)),
        "max_load_times": max(0, max_load_times),
    }


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
    max_bocha, max_anysearch, max_extract_times, _ = resolve_radar_tool_quotas(ctx)
    knowledge = resolve_radar_knowledge_config(ctx)
    return {
        "current_message": HumanMessage(
            content=(
                f"{request.query}\n\n"
                "请严格按当前节点系统提示输出单个 JSON 对象，"
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
            "max_bocha": str(max_bocha),
            "max_anysearch": str(max_anysearch),
            "max_extract_times": str(max_extract_times),
            # 知识库开关（终评模板用 knowledge_max_load_times 说明调用上限）
            "knowledge_enabled": "true" if knowledge["enabled"] else "false",
            "knowledge_max_docs": str(knowledge["max_docs"]),
            "knowledge_max_load_times": str(knowledge["max_load_times"]),
            # 采集节点写入前给占位，避免终评模板残留未替换花括号
            "evidence_briefs": "[]",
            "discarded_briefs": "[]",
        },
        "edges_var": {},
        "persistence_edges_var": {},
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


def _normalize_optional_str(value: Any) -> Optional[str]:
    """将可选字符串去空白；空则 None。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_signal_summary(value: Any) -> Optional[str]:
    """
        规范化一句话信号简述。

        Returns:
            去空白后的简述；空则 None
    """
    return _normalize_optional_str(value)


def _is_level_only_summary(summary: str) -> bool:
    """简述是否仅为 S1-S4 等级码（禁止作为 UI 主文案）。"""
    return bool(re.fullmatch(r"S[1-4]", summary.strip(), flags=re.IGNORECASE))


def _parse_optional_int(value: Any) -> Optional[int]:
    """可选整数解析。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
    """解析 evidences 列表（补 evidence_no / source_type）。"""
    if not isinstance(raw, list):
        return []
    items: List[RadarEventEvidenceItem] = []
    for idx, ev in enumerate(raw):
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
        source_level = ev.get("source_level") or ev.get("sourceLevel")
        doc_id = ev.get("doc_id", ev.get("docId"))
        st = str(ev.get("source_type") or ev.get("sourceType") or "").strip().lower()
        if not st:
            st = "knowledge_base" if doc_id else "web"
        eno = ev.get("evidence_no", ev.get("evidenceNo", ev.get("temp_id", ev.get("tempId"))))
        try:
            evidence_no = int(eno) if eno is not None and eno != "" else idx
        except (TypeError, ValueError):
            evidence_no = idx
        items.append(
            RadarEventEvidenceItem(
                evidence_no=evidence_no,
                source_type=st,
                doc_id=doc_id,
                title=ev.get("title"),
                summary=ev.get("summary"),
                quote=ev.get("quote"),
                url=url_str,
                publish_date=ev.get("publish_date") or ev.get("publishDate"),
                source_host=str(host) if host else None,
                authority_tier=str(tier) if tier else None,
                source_level=str(source_level).strip().upper() if source_level else None,
                content_grade=ev.get("content_grade") or ev.get("contentGrade"),
                cite_reason=ev.get("cite_reason") or ev.get("citeReason"),
                kept=_as_bool(ev.get("kept", True), True),
            )
        )
    return items


def _parse_score_items(raw: Any) -> List[RadarEventScoreItem]:
    """解析 score_items 列表。"""
    if not isinstance(raw, list):
        return []
    items: List[RadarEventScoreItem] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        raw_score = row.get("score")
        score: Optional[int] = None
        if raw_score is not None and raw_score != "":
            try:
                score = int(raw_score)
            except (TypeError, ValueError):
                score = None
        nos_raw = row.get("evidence_nos") or row.get("evidenceNos") or []
        evidence_nos: List[int] = []
        if isinstance(nos_raw, list):
            for n in nos_raw:
                try:
                    evidence_nos.append(int(n))
                except (TypeError, ValueError):
                    continue
        items.append(
            RadarEventScoreItem(
                code=code,
                score=score,
                score_reason=row.get("score_reason") or row.get("scoreReason"),
                evidence_nos=evidence_nos,
            )
        )
    return items


def _kept_evidence_valid(ev: RadarEventEvidenceItem) -> bool:
    """kept 证据是否满足「有分必有据」：KB 需 doc_id；web 需 http url。"""
    st = str(ev.source_type or "web").lower()
    if st == "knowledge_base":
        return bool(str(ev.doc_id or "").strip())
    if st == "web":
        return bool(ev.url and str(ev.url).startswith("http"))
    return bool(ev.url and str(ev.url).startswith("http")) or bool(str(ev.doc_id or "").strip())


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


def parse_radar_event_score_from_obj(obj: Dict[str, Any]) -> RadarEventScoreResult:
    """
        从已解析的 dict 构造 RadarEventScoreResult。

        Args:
            obj: 评分 JSON 对象（可为含 radar_event_score 包装层）

        Returns:
            RadarEventScoreResult

        Raises:
            ValueError: 缺关键字段或分值非法
    """
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
    score_items = _parse_score_items(obj.get("score_items") or obj.get("scoreItems") or [])

    web_hit_count = int(obj.get("web_hit_count") or obj.get("webHitCount") or 0)
    kb_hit_count = int(obj.get("kb_hit_count") or obj.get("kbHitCount") or 0)
    if web_hit_count <= 0:
        web_hit_count = sum(
            1 for e in evidences if e.kept and str(e.source_type or "").lower() == "web"
        )
    if kb_hit_count <= 0:
        kb_hit_count = sum(
            1
            for e in evidences
            if e.kept and str(e.source_type or "").lower() == "knowledge_base"
        )

    # 先对齐排除语义：模型常只写 admission_hint=expired，未同步 expired_or_done
    admission_hint = _normalize_admission_hint(
        obj.get("admission_hint") or obj.get("admissionHint")
    )
    if not exhibition_related:
        admission_hint = "reject_unrelated"
    if admission_hint == "reject_unrelated":
        exhibition_related = False
    if admission_hint == "expired" or expired_or_done:
        expired_or_done = True
        admission_hint = "expired"

    # 3. 排除类清空分数；有分必有据（kept 须 doc_id 或 url，web 仍须 url）
    total_score: Optional[int]
    excluded = (not exhibition_related) or expired_or_done
    if excluded:
        evidence_score = None
        specificity_score = None
        total_score = None
        for item in score_items:
            item.score = None
    else:
        if evidence_score is None and specificity_score is None:
            total_score = None
        else:
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
            kept_valid = [e for e in evidences if e.kept and _kept_evidence_valid(e)]
            if total_score is not None and total_score > 0 and not kept_valid:
                raise ValueError(
                    "有分必有据：total_score>0 时 kept 证据须含 doc_id 或有效 url（web 必须 url）"
                )
        # score_items 缺分时用顶层回填
        for item in score_items:
            if item.score is not None:
                continue
            if item.code == "evidence_score" and evidence_score is not None:
                item.score = evidence_score
            elif item.code == "specificity_score" and specificity_score is not None:
                item.score = specificity_score
        # 无 score_items 时按顶层合成，便于 Java 统一契约
        if not score_items and (evidence_score is not None or specificity_score is not None):
            score_items = [
                RadarEventScoreItem(
                    code="evidence_score",
                    score=evidence_score,
                    score_reason=obj.get("score_reason") or obj.get("scoreReason"),
                    evidence_nos=[],
                ),
                RadarEventScoreItem(
                    code="specificity_score",
                    score=specificity_score,
                    score_reason=obj.get("score_reason") or obj.get("scoreReason"),
                    evidence_nos=[],
                ),
            ]

    tags_raw = obj.get("tags") or []
    tags = [str(t).strip() for t in tags_raw if str(t).strip()] if isinstance(tags_raw, list) else []

    signal_summary = _normalize_signal_summary(
        obj.get("signal_summary") or obj.get("signalSummary")
    )
    signal_time = _normalize_optional_str(
        obj.get("signal_time") or obj.get("signalTime")
    )
    signal_time_evidence_no = _parse_optional_int(
        obj.get("signal_time_evidence_no") or obj.get("signalTimeEvidenceNo")
    )
    # 有分必有 UI 简述；无信号时间不得标 pass
    has_score = total_score is not None and total_score > 0
    if has_score:
        if not signal_summary:
            raise ValueError("有分必有 signal_summary：total_score>0 时须输出一句话展厅信号简述")
        if _is_level_only_summary(signal_summary):
            raise ValueError("signal_summary 禁止仅为 S1-S4 等级码")
        if not signal_time and admission_hint == "pass":
            admission_hint = "pending_verify"

    return RadarEventScoreResult(
        exhibition_related=exhibition_related,
        subject_confidence=_normalize_subject_confidence(
            obj.get("subject_confidence") or obj.get("subjectConfidence")
        ),
        space_object=obj.get("space_object") or obj.get("spaceObject"),
        action=obj.get("action"),
        place=obj.get("place"),
        time_text=obj.get("time_text") or obj.get("timeText"),
        signal_summary=signal_summary,
        signal_time=signal_time,
        signal_time_evidence_no=signal_time_evidence_no,
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
        score_items=score_items,
        evidences=evidences,
        discarded=_parse_discarded(obj.get("discarded") or []),
        search_count=int(obj.get("search_count") or obj.get("searchCount") or 0),
        extract_count=int(obj.get("extract_count") or obj.get("extractCount") or 0),
        web_hit_count=web_hit_count,
        kb_hit_count=kb_hit_count,
    )


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
    return parse_radar_event_score_from_obj(obj)


def resolve_score_from_flow_result(result: Dict[str, Any]) -> RadarEventScoreResult:
    """
        优先从 edges_var / persistence_edges_var 的 radar_event_score 解析；
        否则回退最后一条 AI 文本。

        Args:
            result: graph.ainvoke 返回的状态

        Returns:
            RadarEventScoreResult

        Raises:
            ValueError: 各路径均无法解析
    """
    # 1. edges_var 优先（终评节点刚写入）
    for bag_name in ("edges_var", "persistence_edges_var"):
        bag = result.get(bag_name) or {}
        if not isinstance(bag, dict):
            continue
        score_obj = bag.get("radar_event_score")
        if isinstance(score_obj, dict) and score_obj:
            logger.info(f"从 {bag_name}.radar_event_score 解析评分结果")
            return parse_radar_event_score_from_obj(score_obj)
        # 兼容：模型未包一层时，exhibition_related 可能直接在 edges_var
        if "exhibition_related" in bag:
            logger.info(f"从 {bag_name} 顶层字段解析评分结果")
            return parse_radar_event_score_from_obj(bag)

    # 2. 回退 AI 文本
    ai_text = extract_last_ai_text(result)
    if not ai_text:
        raise ValueError("流程未返回 radar_event_score（edges_var 与 AI 文本均空）")
    logger.info("从最后一条 AI 文本解析评分结果（edges_var 未命中）")
    return parse_radar_event_score_from_ai_text(ai_text)


@router.post("/huayuan/radar-event-score", response_model=HuayuanRadarEventResponse)
async def huayuan_radar_event_score(
    request: HuayuanRadarEventRequest,
) -> HuayuanRadarEventResponse:
    """
        华院规则二评分接口：三节点流水线（规划 → 并行采集 → 终评），返回两维分与证据链。

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
    max_bocha, max_anysearch, max_extract_times, max_results = resolve_radar_tool_quotas(
        ctx_body
    )
    knowledge = resolve_radar_knowledge_config(ctx_body)
    document_tool_base_url = ""

    logger.info(
        f"[华院RadarEvent请求开始] trace_id={trace_id}, "
        f"company={company.company_name}, stock_code={company.stock_code}, "
        f"event_job_id={ctx_body.event_job_id}, "
        f"max_bocha={max_bocha}, max_anysearch={max_anysearch}, "
        f"knowledge_enabled={knowledge['enabled']}, "
        f"knowledge_max_docs={knowledge['max_docs']}, "
        f"knowledge_max_load_times={knowledge['max_load_times']}"
    )

    runtime_ctx = build_radar_event_context_from_request(
        company_name=company.company_name,
        stock_code=company.stock_code or "",
        aliases=company.aliases,
        max_bocha=max_bocha,
        max_anysearch=max_anysearch,
        max_extract_times=max_extract_times,
        max_results_per_search=max_results,
        max_extract_chars=DEFAULT_MAX_EXTRACT_CHARS,
        event_job_id=ctx_body.event_job_id,
        trace_id=trace_id,
        company_id=company.company_id,
        knowledge_enabled=knowledge["enabled"],
        knowledge_max_docs=knowledge["max_docs"],
        knowledge_max_load_times=knowledge["max_load_times"],
        knowledge_max_chars=DEFAULT_KNOWLEDGE_MAX_CHARS,
        document_tool_base_url=document_tool_base_url,
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
                "langfuse_tags": ["huayuan_radar_event", "api", "pipeline_v2"],
                "flow_key": HUAYUAN_RADAR_EVENT_FLOW_KEY,
                "source": "huayuan_radar_event_api",
                "event_job_id": str(ctx_body.event_job_id or ""),
            }

        with HuayuanRadarEventContext(runtime_ctx):
            result = await graph.ainvoke(initial_state, config)

        # 3. 优先 edges_var.radar_event_score，回退 AI 文本
        score_result = resolve_score_from_flow_result(result)

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
            f"search_count={score_result.search_count}, "
            f"bocha={runtime_ctx.bocha_count}, anysearch={runtime_ctx.anysearch_count}, "
            f"knowledge_enabled={runtime_ctx.knowledge.enabled}, "
            f"knowledge_hit_rate={runtime_ctx.knowledge.hit_rate:.2f}, "
            f"knowledge_whitelist={len(runtime_ctx.knowledge.recalled_doc_ids)}, "
            f"knowledge_load_count={runtime_ctx.knowledge.load_count}"
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
