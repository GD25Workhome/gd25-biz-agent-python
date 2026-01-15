"""
Session缓存模型
"""
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import JSONB

from backend.infrastructure.database.base import Base, TABLE_PREFIX


class SessionCache(Base):
    """Session缓存模型"""
    
    __tablename__ = f"{TABLE_PREFIX}session_cache"
    
    id = Column(
        String(200),
        primary_key=True,
        comment="Session ID（直接使用session_id）"
    )
    data_info = Column(
        JSONB,
        nullable=False,
        comment="Session上下文字典数据（JSON格式）"
    )
    
    def __repr__(self):
        return f"<SessionCache(id={self.id})>"
