"""
Pipeline Embedding 记录表模型（pipeline_embedding_records）
设计文档：cursor_docs/022801-pipeline_embedding_records表与model-repository技术设计.md
"""
from sqlalchemy import Column, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSON

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    Vector = None
    HAS_PGVECTOR = False
    import warnings
    warnings.warn(
        "pgvector not installed. Vector columns will be defined as Text. "
        "Please install pgvector: pip install pgvector"
    )

from backend.infrastructure.database.base import (
    Base,
    UlidIdMixin,
    AuditFieldsMixin,
)


PIPELINE_TABLE_PREFIX = "pipeline_"


class PipelineEmbeddingRecordBusinessMixin:
    """pipeline_embedding_records 业务字段。"""

    embedding_str = Column(
        Text,
        nullable=True,
        comment="用于生成 embedding 的文本",
    )
    embedding_value = Column(
        Vector(2048) if HAS_PGVECTOR else Text,
        nullable=True,
        comment="Embedding 向量值（2048 维）",
    )
    embedding_type = Column(
        String(50),
        nullable=True,
        comment="类型：Q（仅提问）、QA（提问+回答）",
    )
    is_published = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否发布",
    )
    type_ = Column(
        "type",
        String(64),
        nullable=True,
        comment="主分类",
    )
    sub_type = Column(
        String(64),
        nullable=True,
        comment="子分类（业务上若为空可用主分类填充）",
    )
    metadata_ = Column(
        "metadata",
        JSON,
        nullable=True,
        comment="扩展元数据",
    )


class PipelineEmbeddingRecordRecord(
    UlidIdMixin,
    PipelineEmbeddingRecordBusinessMixin,
    AuditFieldsMixin,
    Base,
):
    """Pipeline Embedding 记录表：pipeline_embedding_records（前缀 pipeline_，业务名 embedding_records）。"""

    __tablename__ = f"{PIPELINE_TABLE_PREFIX}embedding_records"

    def __repr__(self) -> str:
        return f"<PipelineEmbeddingRecordRecord(id={self.id})>"
