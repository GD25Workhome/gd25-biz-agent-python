"""
数据集合模型
用于存储 dataSet 的元信息（名称、路径、schema 等）。
设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
"""
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, generate_ulid


PIPELINE_TABLE_PREFIX = "pipeline_"


class DataSetsRecord(Base):
    """数据集合模型"""

    __tablename__ = f"{PIPELINE_TABLE_PREFIX}data_sets"

    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="ULID 或业务 ID",
    )
    name = Column(
        String(200),
        nullable=False,
        comment="名称",
    )
    path_id = Column(
        String(50),
        ForeignKey(f"{PIPELINE_TABLE_PREFIX}data_sets_path.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="关联 dataSetsPath.id",
    )
    input_schema = Column(
        JSONB,
        nullable=True,
        comment="input 的 JSON Schema",
    )
    output_schema = Column(
        JSONB,
        nullable=True,
        comment="output 的 JSON Schema",
    )
    metadata_ = Column(
        "metadata",
        JSONB,
        nullable=True,
        comment="扩展元数据",
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
        return f"<DataSetsRecord(id={self.id}, name={self.name})>"
