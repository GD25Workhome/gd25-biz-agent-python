"""
数据集合文件夹模型
用于存储 dataSets 的树形目录结构。
设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
"""
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base


# 本模块使用 pipeline_ 前缀，与项目其他表 gd2502_ 区分
PIPELINE_TABLE_PREFIX = "pipeline_"


class DataSetsPathRecord(Base):
    """数据集合文件夹模型"""

    __tablename__ = f"{PIPELINE_TABLE_PREFIX}data_sets_path"

    id = Column(
        String(50),
        primary_key=True,
        index=True,
        comment="可主动设置，用于路径拼接",
    )
    id_path = Column(
        String(500),
        nullable=True,
        index=True,
        comment="上级路径。根节点为空；下级为上级 id；多级用英文逗号拼接",
    )
    name = Column(
        String(200),
        nullable=False,
        comment="名称",
    )
    description = Column(
        Text,
        nullable=True,
        comment="描述",
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
        return f"<DataSetsPathRecord(id={self.id}, name={self.name})>"
