"""
embedding_import 核心包

提供从 blood_pressure_session_records 表读取数据、组装状态、执行 embedding_agent 流程的工具。

注意：repository、runner 会依赖 DB/Langfuse，不在此处导入，避免单测仅测 history_parser 时加载 pgvector 等。
使用处请从 core.repository、core.runner 直接导入。
"""
from scripts.embedding_import.core.config import (
    DEFAULT_BATCH_SIZE,
    FLOW_KEY,
    TOKEN_ID_PLACEHOLDER,
    SESSION_ID_PREFIX,
)
from scripts.embedding_import.core.history_parser import parse_history_messages
from scripts.embedding_import.core.state_builder import (
    build_initial_state_from_record,
    build_prompt_vars_from_record,
)

__all__ = [
    "DEFAULT_BATCH_SIZE",
    "FLOW_KEY",
    "TOKEN_ID_PLACEHOLDER",
    "SESSION_ID_PREFIX",
    "parse_history_messages",
    "build_initial_state_from_record",
    "build_prompt_vars_from_record",
]
