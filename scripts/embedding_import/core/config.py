"""
embedding_import 常量与默认配置

见设计文档 §8.3。
"""

# 默认批量大小；入口未指定 --limit 时使用
DEFAULT_BATCH_SIZE: int = 400

# 流程名，与 config/flows/embedding_agent/flow.yaml 的 name 一致
FLOW_KEY: str = "embedding_agent"

# 批量脚本占位 token_id（无真实 Token 时使用）
TOKEN_ID_PLACEHOLDER: str = "embedding_import"

# 用于生成 session_id 的前缀，如 embedding_import_{record.id}
SESSION_ID_PREFIX: str = "embedding_import_"
