"""
pipeline 模型子包
设计文档：cursor_docs/022801-pipeline_embedding_records表与model-repository技术设计.md
"""
from backend.infrastructure.database.models.pipeline.pipeline_embedding_record import (
    METADATA_KEY_BATCH_JOB_ID,
    METADATA_KEY_BATCH_TASK_ID,
    PipelineEmbeddingRecordRecord,
)

__all__ = [
    "METADATA_KEY_BATCH_JOB_ID",
    "METADATA_KEY_BATCH_TASK_ID",
    "PipelineEmbeddingRecordRecord",
]
