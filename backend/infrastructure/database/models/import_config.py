"""
导入配置模型
用于存储数据导入的配置信息，由后台强绑定解析。
设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
"""
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, generate_ulid


PIPELINE_TABLE_PREFIX = "pipeline_"


class ImportConfigRecord(Base):
    """导入配置模型"""

    __tablename__ = f"{PIPELINE_TABLE_PREFIX}import_config"

    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="ULID",
    )
    name = Column(
        String(200),
        nullable=False,
        comment="配置名称",
    )
    description = Column(
        Text,
        nullable=True,
        comment="描述",
    )
    import_config = Column(
        JSONB,
        nullable=True,
        comment="导入逻辑配置，由后台强绑定",
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
        return f"<ImportConfigRecord(id={self.id}, name={self.name})>"
