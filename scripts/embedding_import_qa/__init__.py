"""
知识库 Embedding 导入脚本包

从 knowledge_base 表读取未处理记录，运行 embedding_knowledge_agent 流程，结果写入 embedding_records。
设计文档：cursor_docs/012901-知识库Embedding导入脚本设计.md
"""
from scripts.embedding_import_qa.core import (
    DEFAULT_BATCH_SIZE,
    FLOW_KEY,
    SESSION_ID_PREFIX,
    build_initial_state_from_record,
)

__all__ = [
    "DEFAULT_BATCH_SIZE",
    "FLOW_KEY",
    "SESSION_ID_PREFIX",
    "build_initial_state_from_record",
]
