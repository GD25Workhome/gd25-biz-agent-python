"""
批次表模型（batch_job）
设计文档：cursor_docs/022603-数据embedding批次表字段设计.md
"""
from sqlalchemy import Column, String, Integer
from sqlalchemy.dialects.postgresql import JSON

from backend.infrastructure.database.base import (
    Base,
    UlidIdMixin,
    AuditFieldsMixin,
)


class BatchJobBusinessMixin:
    """batch_job 业务字段：job_type、code、total_count、query_params。"""

    job_type = Column(
        String(64),
        nullable=False,
        comment="批次任务类型（如 embedding、data_clean 等）",
    )
    code = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="批次编码，唯一",
    )
    total_count = Column(
        Integer,
        nullable=False,
        comment="本批次待 embedding 条数",
    )
    query_params = Column(
        JSON,
        nullable=True,
        comment="查询参数（如筛选条件、分页等）",
    )


class BatchJobRecord(UlidIdMixin, BatchJobBusinessMixin, AuditFieldsMixin, Base):
    """批次表：batch_job。"""

    __tablename__ = "batch_job"

    def __repr__(self) -> str:
        return f"<BatchJobRecord(id={self.id}, code={self.code})>"
