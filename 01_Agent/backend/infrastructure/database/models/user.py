"""
用户模型
"""
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, TABLE_PREFIX, generate_ulid


class User(Base):
    """用户模型"""
    
    __tablename__ = f"{TABLE_PREFIX}users"
    
    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="用户ID（ULID）"
    )
    user_name = Column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="用户名（唯一）"
    )
    user_info = Column(
        JSONB,
        nullable=True,
        comment="用户信息（JSON格式）"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_func.now(),
        default=sql_func.now(),
        comment="创建时间（自动生成）"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=sql_func.now(),
        comment="更新时间（自动更新）"
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, user_name={self.user_name})>"

