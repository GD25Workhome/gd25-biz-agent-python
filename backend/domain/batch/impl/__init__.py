"""
批次任务创建/执行具体实现（按业务聚合）。
"""
from backend.domain.batch.impl.pipeline_embedding_impl import PipelineEmbeddingCreateHandler

__all__ = [
    "PipelineEmbeddingCreateHandler",
]
