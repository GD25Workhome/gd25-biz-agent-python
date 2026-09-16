"""
Milvus 向量库基础设施包（雷达新闻知识库专用）。

⚠️ 与 `backend/infrastructure/database/vector_connection.py`（pgvector，医疗线在用）
完全独立：pgvector 那条链路不动，Milvus 是本次新接入的独立客户端。
"""
from backend.infrastructure.milvus.radar_news_doc_store import (
    RadarNewsDocStore,
    get_milvus_store,
    reset_milvus_store,
)

__all__ = ["RadarNewsDocStore", "get_milvus_store", "reset_milvus_store"]
