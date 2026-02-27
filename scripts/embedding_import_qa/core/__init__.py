"""
embedding_import_qa 核心包

从 knowledge_base 表读取未处理记录、组装 state、执行 embedding_knowledge_agent 流程。
设计文档：cursor_docs/012901-知识库Embedding导入脚本设计.md
"""
from scripts.embedding_import_qa.core.config import (
    DEFAULT_BATCH_SIZE,
    FLOW_KEY,
    KNOWLEDGE_BASE_TABLE_NAME,
    SESSION_ID_PREFIX,
    TOKEN_ID_PLACEHOLDER,
)
from scripts.embedding_import_qa.core.state_builder import build_initial_state_from_record

__all__ = [
    "DEFAULT_BATCH_SIZE",
    "FLOW_KEY",
    "KNOWLEDGE_BASE_TABLE_NAME",
    "SESSION_ID_PREFIX",
    "TOKEN_ID_PLACEHOLDER",
    "build_initial_state_from_record",
]
