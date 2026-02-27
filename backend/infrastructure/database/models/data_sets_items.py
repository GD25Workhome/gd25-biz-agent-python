"""
数据项模型
用于存储 dataSet 中的实际数据（input、output、metadata 等）。
设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
"""
from sqlalchemy import Column, String, SmallInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, generate_ulid


PIPELINE_TABLE_PREFIX = "pipeline_"


class DataSetsItemsRecord(Base):
    """数据项"""

    __tablename__ = f"{PIPELINE_TABLE_PREFIX}data_sets_items"

    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="ULID",
    )
    dataset_id = Column(
        String(50),
        ForeignKey(f"{PIPELINE_TABLE_PREFIX}data_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联 dataSets.id",
    )
    unique_key = Column(
        String(200),
        nullable=True,
        index=True,
        comment="业务唯一 key",
    )
    input = Column(
        JSONB,
        nullable=True,
        comment="输入数据",
    )
    output = Column(
        JSONB,
        nullable=True,
        comment="输出数据",
    )
    metadata_ = Column(
        "metadata",
        JSONB,
        nullable=True,
        comment="扩展元数据",
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="1=激活，0=废弃",
    )
    source = Column(
        String(200),
        nullable=True,
        comment="来源",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_func.now(),
        default=sql_func.now(),
        comment="创建时间（自动生成）",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=sql_func.now(),
        comment="更新时间（自动更新）",
    )

    def __repr__(self) -> str:
        return f"<DataSetsItemsRecord(id={self.id}, dataset_id={self.dataset_id})>"
