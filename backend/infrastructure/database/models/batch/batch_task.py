"""
子任务表模型（batch_task）
设计文档：cursor_docs/022603-数据embedding批次表字段设计.md
"""
from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import JSON

from backend.infrastructure.database.base import (
    Base,
    UlidIdMixin,
    AuditFieldsMixin,
)


class BatchTaskBusinessMixin:
    """batch_task 业务字段。"""

    job_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="关联批次表 batch_job.id",
    )
    source_table_id = Column(
        String(50),
        nullable=True,
        comment="来源表 ID（业务主键或来源系统 ID）",
    )
    source_table_name = Column(
        String(128),
        nullable=True,
        comment="来源表名（如 pipeline_data_items_rewritten）",
    )
    status = Column(
        String(32),
        nullable=True,
        comment="状态（如 pending/running/success/failed）",
    )
    runtime_params = Column(
        JSON,
        nullable=True,
        comment="运行时参数",
    )
    redundant_key = Column(
        String(256),
        nullable=True,
        comment="冗余 key（去重/幂等用）",
    )
    execution_result = Column(
        Text,
        nullable=True,
        comment="执行返回结果",
    )
    execution_error_message = Column(
        Text,
        nullable=True,
        comment="执行失败信息（含异常堆栈）",
    )
    execution_return_key = Column(
        String(256),
        nullable=True,
        comment="执行返回标识 key",
    )


class BatchTaskRecord(UlidIdMixin, BatchTaskBusinessMixin, AuditFieldsMixin, Base):
    """子任务表：batch_task。"""

    __tablename__ = "batch_task"

    def __repr__(self) -> str:
        return f"<BatchTaskRecord(id={self.id}, job_id={self.job_id})>"
