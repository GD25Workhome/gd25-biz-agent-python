"""
Rewritten 批次模型

用于集中管理 rewritten 批次的 batch_code 及元数据。
设计文档：cursor_docs/021101-Rewritten批次表与创建流程设计.md
"""
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, generate_ulid


PIPELINE_TABLE_PREFIX = "pipeline_"


class RewrittenBatchRecord(Base):
    """Rewritten 批次记录"""

    __tablename__ = f"{PIPELINE_TABLE_PREFIX}rewritten_batches"

    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="ULID",
    )
    batch_code = Column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="批次编码",
    )
    total_count = Column(
        Integer,
        nullable=False,
        comment="本批次数据项总量",
    )
    create_params = Column(
        JSONB,
        nullable=True,
        comment="创建参数（JSON，含 dataset_id/dataset_ids 等）",
    )
    status = Column(
        String(20),
        nullable=True,
        comment="批次级状态（可选）",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_func.now(),
        default=sql_func.now(),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=sql_func.now(),
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<RewrittenBatchRecord(id={self.id}, batch_code={self.batch_code})>"
