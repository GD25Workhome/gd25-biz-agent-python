"""
从表记录组装 FlowState / prompt_vars

见设计文档 §3.2、§3.4、§8.5。
"""
from datetime import datetime
from typing import Any, Dict, List, TYPE_CHECKING

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from backend.domain.state import FlowState

from scripts.embedding_import.core.config import TOKEN_ID_PLACEHOLDER
from scripts.embedding_import.core.history_parser import parse_history_messages

if TYPE_CHECKING:
    from backend.infrastructure.database.models.blood_pressure_session import (
        BloodPressureSessionRecord,
    )


def _safe_str(v: Any) -> str:
    """None 或空转为 ''，否则 str。"""
    if v is None:
        return ""
    s = str(v).strip()
    return s if s else ""


def _format_history_messages_for_prompt(msgs: List[BaseMessage]) -> str:
    """将 history_messages 格式化为「用户: ...\\n助手: ...」供 prompt 占位符使用。"""
    parts: List[str] = []
    for m in msgs:
        c = getattr(m, "content", None) or ""
        text = _safe_str(c)
        if not text:
            continue
        if isinstance(m, HumanMessage):
            parts.append(f"用户: {text}")
        elif isinstance(m, AIMessage):
            parts.append(f"助手: {text}")
        else:
            parts.append(text)
    return "\n".join(parts)


def build_prompt_vars_from_record(record: "BloodPressureSessionRecord") -> Dict[str, Any]:
    """
    从表字段组装 prompt_vars（user_info、current_date、ai_response、manual_ext 等）。
    与 20-ext_agent.md 占位符一致。
    """
    prompt_vars: Dict[str, Any] = {}

    prompt_vars["current_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    user_info: Dict[str, Any] = {}
    for key, attr in [
        ("年龄", "age"),
        ("疾病", "disease"),
        ("血压", "blood_pressure"),
        ("症状", "symptom"),
        ("用药", "medication"),
        ("用药情况", "medication_status"),
        ("习惯", "habit"),
    ]:
        v = getattr(record, attr, None)
        if v is not None and str(v).strip():
            user_info[key] = v
    prompt_vars["user_info"] = user_info if user_info else None

    prompt_vars["ai_response"] = _safe_str(getattr(record, "new_session_response", None))
    prompt_vars["manual_ext"] = _safe_str(getattr(record, "ext", None))

    current_msg = _safe_str(getattr(record, "new_session", None))
    prompt_vars["current_message"] = current_msg

    history_msgs = parse_history_messages(record)
    prompt_vars["history_messages"] = _format_history_messages_for_prompt(history_msgs)

    return prompt_vars


def build_initial_state_from_record(
    record: "BloodPressureSessionRecord",
    session_id: str,
    trace_id: str,
) -> FlowState:
    """
    根据 3.2、3.4 组装完整 FlowState。
    含 current_message、history_messages、prompt_vars、flow_msgs、token_id 等。
    """
    prompt_vars = build_prompt_vars_from_record(record)
    history_messages = parse_history_messages(record)
    new_session = _safe_str(getattr(record, "new_session", None))
    current_message = HumanMessage(content=new_session) if new_session else HumanMessage(content="")
    
    # 在 prompt_vars 中增加数据源信息
    prompt_vars["source_id"] = record.id  # 数据源记录ID
    prompt_vars["source_table_name"] = "blood_pressure_session_records"  # 数据来源表名
    
    return {
        "current_message": current_message,
        "history_messages": history_messages,
        "flow_msgs": [],
        "session_id": session_id,
        "token_id": TOKEN_ID_PLACEHOLDER,
        "trace_id": trace_id,
        "prompt_vars": prompt_vars,
    }
