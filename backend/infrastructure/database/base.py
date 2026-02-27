"""
SQLAlchemy Base 定义
设计文档：cursor_docs/022603-数据embedding批次表字段设计.md
"""
from ulid import ULID
from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func as sql_func

# 表名前缀常量
TABLE_PREFIX = "gd2502_"

Base = declarative_base()


def generate_ulid() -> str:
    """
    生成 ULID（Universally Unique Lexicographically Sortable Identifier）
    
    ULID 具有以下特性：
    - 26个字符（Base32编码）
    - 48位时间戳（毫秒） + 80位随机数
    - 按字典序排序即按时间排序
    - 全局唯一性
    
    Returns:
        str: ULID 字符串（26个字符）
    """
    return str(ULID())


class UlidIdMixin:
    """主键 id（ULID），供带审计字段的 batch 等表复用。"""

    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="ULID",
    )


class AuditFieldsMixin:
    """审计与软删字段：version、is_deleted、create_time、update_time。"""

    version = Column(
        Integer,
        nullable=False,
        default=0,
        comment="版本号（自增，非乐观锁）",
    )
    is_deleted = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="软删标记",
    )
    create_time = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_func.now(),
        default=sql_func.now(),
        comment="创建时间",
    )
    update_time = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="更新时间（更新时由仓储赋值）",
    )

