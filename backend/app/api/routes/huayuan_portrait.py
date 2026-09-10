"""
华院五维画像评分路由

对接 exhibition：POST /api/v1/huayuan/portrait
无 Session；固定流程 huayuan_react_agent；解析失败返回 500（R1-a）。
"""
from __future__ import annotations

import json
import logging
import os
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
    PortraitDimension,
    PortraitEvidence,
    PortraitResult,
)
from backend.domain.flows.manager import FlowManager
from backend.domain.state import FlowState
from backend.domain.tools.huayuan_portrait_context import (
    HuayuanPortraitContext,
    build_portrait_context_from_request,
)
from backend.infrastructure.observability.langfuse_handler import create_langfuse_handler

logger = logging.getLogger(__name__)
router = APIRouter()

HUAYUAN_PORTRAIT_FLOW_KEY = "huayuan_react_agent"
DEFAULT_MAX_LOAD_TIMES = 3
DEFAULT_MAX_CHARS = 12000
VALID_TIERS = {"strong", "stronger", "medium", "weak_or_unknown"}
VALID_FACT_STATUS = {"confirmed", "inferred", "unknown", "conflict"}


def _dumps_prompt_var(value: Any) -> str:
    """将对象序列化为提示词占位符字符串。"""
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


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
    return {
        "current_message": HumanMessage(
            content=(
                f"{request.query}\n\n"
                "请严格输出规定的单个 JSON 对象（含全部五维 dimensions），不要使用 Markdown 代码围栏。"
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
            "file_metas_json": _dumps_prompt_var(ctx.file_metas),
            "stats_json": _dumps_prompt_var(ctx.stats),
            "rule_version": ctx.rule_version or "",
            "max_load_times": str(
                ctx.max_load_times if ctx.max_load_times is not None else DEFAULT_MAX_LOAD_TIMES
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
    # 去掉常见 Markdown 围栏
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
    """规范化证据状态。"""
    s = str(status or "").strip().lower()
    return s if s in VALID_FACT_STATUS else "unknown"


def _prefill_tier_for_code(rule_prefill: Optional[Dict[str, Any]], code: str) -> Optional[str]:
    """从 rule_prefill 读取某维 tier。"""
    if not isinstance(rule_prefill, dict):
        return None
    item = rule_prefill.get(code)
    if isinstance(item, dict) and item.get("tier"):
        return _normalize_tier(item.get("tier"))
    return None


def ensure_all_dimensions(
    portrait: PortraitResult,
    rule_prefill: Optional[Dict[str, Any]],
) -> PortraitResult:
    """
        确保五维齐全（R3-a）：缺失维用 prefill 或 weak_or_unknown 补齐。

        Args:
            portrait: 已解析的 portrait
            rule_prefill: 规则预填

        Returns:
            补齐后的 PortraitResult
    """
    by_code: Dict[str, PortraitDimension] = {}
    for dim in portrait.dimensions:
        code = str(dim.code).strip()
        if code in REQUIRED_DIM_CODES and code not in by_code:
            by_code[code] = PortraitDimension(
                code=code,
                tier=_normalize_tier(dim.tier),
                fact_status=_normalize_fact_status(dim.fact_status),
                evidence=dim.evidence or [],
                missing_reason=dim.missing_reason,
            )

    filled: List[PortraitDimension] = []
    for code in REQUIRED_DIM_CODES:
        if code in by_code:
            filled.append(by_code[code])
            continue
        prefill_tier = _prefill_tier_for_code(rule_prefill, code)
        if prefill_tier:
            filled.append(
                PortraitDimension(
                    code=code,
                    tier=prefill_tier,
                    fact_status="confirmed",
                    evidence=[],
                    missing_reason=None,
                )
            )
        else:
            filled.append(
                PortraitDimension(
                    code=code,
                    tier="weak_or_unknown",
                    fact_status="unknown",
                    evidence=[],
                    missing_reason="模型未返回该维，已按无依据补齐",
                )
            )

    portrait.dimensions = filled
    return portrait


def parse_portrait_from_ai_text(
    text: str,
    rule_prefill: Optional[Dict[str, Any]],
) -> PortraitResult:
    """
        解析模型输出为 PortraitResult；失败抛 ValueError（由路由转 500）。

        Args:
            text: 模型最终文本
            rule_prefill: 用于补齐缺失维

        Returns:
            PortraitResult

        Raises:
            ValueError: 无法解析 JSON 或缺少 portrait 结构
    """
    obj = _extract_json_object(text)
    if not obj:
        raise ValueError("无法从模型输出中解析 JSON 对象")

    # 兼容外层包了 portrait
    if "dimensions" not in obj and isinstance(obj.get("portrait"), dict):
        obj = obj["portrait"]

    if "dimensions" not in obj:
        raise ValueError("JSON 中缺少 dimensions 字段")

    raw_dims = obj.get("dimensions") or []
    if not isinstance(raw_dims, list):
        raise ValueError("dimensions 必须是数组")

    dimensions: List[PortraitDimension] = []
    for item in raw_dims:
        if not isinstance(item, dict):
            continue
        evidence_list: List[PortraitEvidence] = []
        for ev in item.get("evidence") or []:
            if isinstance(ev, dict):
                evidence_list.append(
                    PortraitEvidence(
                        ref_id=ev.get("ref_id", ev.get("refId")),
                        quote=ev.get("quote"),
                    )
                )
        dimensions.append(
            PortraitDimension(
                code=str(item.get("code") or "").strip(),
                tier=_normalize_tier(item.get("tier")),
                fact_status=_normalize_fact_status(item.get("fact_status") or item.get("factStatus")),
                evidence=evidence_list,
                missing_reason=item.get("missing_reason") or item.get("missingReason"),
            )
        )

    portrait = PortraitResult(
        dimensions=dimensions,
        loaded_file_ids=[str(x) for x in (obj.get("loaded_file_ids") or obj.get("loadedFileIds") or [])],
        discarded_file_ids=[
            str(x) for x in (obj.get("discarded_file_ids") or obj.get("discardedFileIds") or [])
        ],
        load_count=int(obj.get("load_count") or obj.get("loadCount") or 0),
    )
    return ensure_all_dimensions(portrait, rule_prefill)


@router.post("/huayuan/portrait", response_model=HuayuanPortraitResponse)
async def huayuan_portrait(request: HuayuanPortraitRequest) -> HuayuanPortraitResponse:
    """
        华院五维画像评分接口：ReAct 按需加载证据并返回候选档位。

        Args:
            request: 画像请求（query + context）

        Returns:
            含 trace_id 与 portrait 的响应

        Raises:
            HTTPException: 流程失败或 portrait 解析失败时 500
    """
    # 1. trace_id 与加载参数
    trace_id = request.trace_id or secrets.token_hex(16)
    ctx_body = request.context
    max_load_times = (
        ctx_body.max_load_times
        if ctx_body.max_load_times is not None
        else DEFAULT_MAX_LOAD_TIMES
    )
    base_url = (ctx_body.document_tool_base_url or "").strip()
    if not base_url:
        base_url = (os.getenv("HUAYUAN_DOCUMENT_TOOL_BASE_URL") or "").strip()

    logger.info(
        f"[华院Portrait请求开始] trace_id={trace_id}, "
        f"file_ids={len(ctx_body.file_ids)}, max_load_times={max_load_times}, "
        f"profile_job_id={ctx_body.profile_job_id}"
    )

    portrait_ctx = build_portrait_context_from_request(
        file_ids=ctx_body.file_ids,
        max_load_times=max_load_times,
        max_chars=DEFAULT_MAX_CHARS,
        document_tool_base_url=base_url,
        profile_job_id=ctx_body.profile_job_id,
        trace_id=trace_id,
    )

    try:
        # 2. 加载流程并执行
        graph = FlowManager.get_flow(HUAYUAN_PORTRAIT_FLOW_KEY)
        initial_state = build_portrait_initial_state(request, trace_id)
        langfuse_handler = create_langfuse_handler(context={"trace_id": trace_id})

        config: Dict[str, Any] = {
            "configurable": {"thread_id": f"huayuan_portrait_{trace_id}"},
        }
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]
            config["metadata"] = {
                "langfuse_tags": ["huayuan_portrait", "api"],
                "flow_key": HUAYUAN_PORTRAIT_FLOW_KEY,
                "source": "huayuan_portrait_api",
                "profile_job_id": str(ctx_body.profile_job_id or ""),
            }

        with HuayuanPortraitContext(portrait_ctx):
            result = await graph.ainvoke(initial_state, config)

        # 3. 解析 portrait（失败 → 500，R1-a）
        ai_text = extract_last_ai_text(result)
        if not ai_text:
            raise ValueError("流程未返回 AI 消息")

        portrait = parse_portrait_from_ai_text(ai_text, ctx_body.rule_prefill)

        # 用运行时真实加载计数回填（若模型漏写）；portrait_ctx 在 with 外仍可读
        if not portrait.loaded_file_ids and portrait_ctx.loaded_file_ids:
            portrait.loaded_file_ids = sorted(portrait_ctx.loaded_file_ids)
        if portrait.load_count <= 0 and portrait_ctx.load_count > 0:
            portrait.load_count = portrait_ctx.load_count

        response_json = portrait.model_dump_json()
        logger.info(
            f"[华院Portrait请求完成] trace_id={trace_id}, "
            f"dims={len(portrait.dimensions)}, load_count={portrait.load_count}"
        )
        return HuayuanPortraitResponse(
            trace_id=trace_id,
            portrait=portrait,
            response=response_json,
        )

    except HTTPException:
        raise
    except ValueError as e:
        # 含 JSON 解析失败
        logger.error(f"华院Portrait处理失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"portrait 解析或处理失败: {str(e)}") from e
    except Exception as e:
        logger.error(f"华院Portrait请求异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}") from e
