"""
embedding_import_qa 常量与默认配置

设计文档：cursor_docs/012901-知识库Embedding导入脚本设计.md §4
"""
from backend.infrastructure.database.models.knowledge_base import KnowledgeBaseRecord

# 默认批量大小；入口未指定 --limit 时使用
DEFAULT_BATCH_SIZE: int = 1000

# 流程名，与 config/flows/embedding_knowledge_agent/flow.yaml 的 name 一致
FLOW_KEY: str = "embedding_knowledge_agent"

# 批量脚本占位 token_id（无真实 Token 时使用）
TOKEN_ID_PLACEHOLDER: str = "embedding_import_qa"

# 用于生成 session_id 的前缀，如 embedding_import_qa_{record.id}
SESSION_ID_PREFIX: str = "embedding_import_qa_"

# 知识库表名（与 EmbeddingRecord.source_table_name、排除已处理逻辑一致）
KNOWLEDGE_BASE_TABLE_NAME: str = KnowledgeBaseRecord.__tablename__
