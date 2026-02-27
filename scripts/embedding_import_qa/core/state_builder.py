"""
从 KnowledgeBaseRecord 组装 FlowState（edges_var、prompt_vars）。

设计文档：cursor_docs/012901-知识库Embedding导入脚本设计.md §3.3.1、§3.5
"""
from typing import Any, Dict, List, TYPE_CHECKING

from backend.domain.state import FlowState

from scripts.embedding_import_qa.core.config import (
    KNOWLEDGE_BASE_TABLE_NAME,
    TOKEN_ID_PLACEHOLDER,
)

if TYPE_CHECKING:
    from backend.infrastructure.database.models.knowledge_base import (
        KnowledgeBaseRecord,
    )


def _safe_str(v: Any) -> str:
    """None 或空转为 ''，否则 str。"""
    if v is None:
        return ""
    s = str(v).strip()
    return s if s else ""


def _safe_list(v: Any) -> List[Any]:
    """None 转为 []，否则确保为 list。"""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return list(v)


def build_initial_state_from_record(
    record: "KnowledgeBaseRecord",
    session_id: str,
    trace_id: str,
) -> FlowState:
    """
    从 KnowledgeBaseRecord 组装完整 FlowState，供 embedding_knowledge_agent 流程使用。

    含 edges_var（scene_summary、optimization_question、input_tags、response_tags、ai_response）、
    prompt_vars（source_id、source_table_name）、session_id、trace_id、token_id 等。
    """
    # edges_var：before_embedding_func 从 state 读取，不查业务表
    scene_summary = _safe_str(getattr(record, "scene_summary", None))
    optimization_question = _safe_str(getattr(record, "optimization_question", None))
    input_tags = _safe_list(getattr(record, "input_tags", None))
    response_tags = _safe_list(getattr(record, "response_tags", None))
    ai_response = _safe_str(getattr(record, "reply_example_or_rule", None))

    edges_var: Dict[str, Any] = {
        "scene_summary": scene_summary,
        "optimization_question": optimization_question,
        "input_tags": input_tags,
        "response_tags": response_tags,
        "ai_response": ai_response,
    }

    # prompt_vars：数据源信息，用于版本号计算与 EmbeddingRecord 写入
    prompt_vars: Dict[str, Any] = {
        "source_id": record.id,
        "source_table_name": KNOWLEDGE_BASE_TABLE_NAME,
    }

    return {
        "edges_var": edges_var,
        "prompt_vars": prompt_vars,
        "session_id": session_id,
        "token_id": TOKEN_ID_PLACEHOLDER,
        "trace_id": trace_id,
        "current_message": None,
        "history_messages": [],
        "flow_msgs": [],
    }
