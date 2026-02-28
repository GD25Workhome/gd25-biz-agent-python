"""
pipeline 仓储子包
设计文档：cursor_docs/022801-pipeline_embedding_records表与model-repository技术设计.md
"""
from backend.infrastructure.database.repository.pipeline.pipeline_embedding_record_repository import (
    PipelineEmbeddingRecordRepository,
)

__all__ = [
    "PipelineEmbeddingRecordRepository",
]
