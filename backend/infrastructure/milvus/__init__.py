"""
Milvus 向量库基础设施包（雷达新闻知识库专用）。

⚠️ 与 `backend/infrastructure/database/vector_connection.py`（pgvector，医疗线在用）
完全独立：pgvector 那条链路不动，Milvus 是本次新接入的独立客户端。

V2（26091607）：默认使用 `RadarNewsChunkStore`（一行一 chunk）。
`get_milvus_store` 为兼容别名，指向 chunk store。
"""
from backend.infrastructure.milvus.radar_news_chunk_store import (
    RadarNewsChunkStore,
    SchemaMismatchError,
    get_milvus_chunk_store,
    reset_milvus_chunk_store,
)
from backend.infrastructure.milvus.radar_news_doc_store import (
    MilvusUnavailableError,
    RadarNewsDocStore,
)

# 召回 / 写入统一走 V2 chunk store
get_milvus_store = get_milvus_chunk_store
reset_milvus_store = reset_milvus_chunk_store

__all__ = [
    "RadarNewsChunkStore",
    "RadarNewsDocStore",
    "MilvusUnavailableError",
    "SchemaMismatchError",
    "get_milvus_chunk_store",
    "reset_milvus_chunk_store",
    "get_milvus_store",
    "reset_milvus_store",
]
