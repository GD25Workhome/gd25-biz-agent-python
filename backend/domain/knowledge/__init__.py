"""
知识库召回与文档直读（画像 / 展厅评分共用）。
"""

from backend.domain.knowledge.news_document_read import load_document_for_agent
from backend.domain.knowledge.radar_kb_recall import (
    chunk_hit_to_doc_brief,
    merge_chunk_hits,
    recall_chunks_for_query,
)

__all__ = [
    "chunk_hit_to_doc_brief",
    "load_document_for_agent",
    "merge_chunk_hits",
    "recall_chunks_for_query",
]
