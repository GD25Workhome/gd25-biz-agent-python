"""
Token缓存模型
"""
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import JSONB

from backend.infrastructure.database.base import Base, TABLE_PREFIX


class TokenCache(Base):
    """Token缓存模型"""
    
    __tablename__ = f"{TABLE_PREFIX}token_cache"
    
    id = Column(
        String(200),
        primary_key=True,
        comment="Token ID（直接使用token_id/user_id）"
    )
    data_info = Column(
        JSONB,
        nullable=False,
        comment="UserInfo对象序列化数据（JSON格式）"
    )
    
    def __repr__(self):
        return f"<TokenCache(id={self.id})>"
