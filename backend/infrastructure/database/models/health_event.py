"""
健康事件模型
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, TABLE_PREFIX, generate_ulid


class HealthEventRecord(Base):
    """健康事件模型"""
    
    __tablename__ = f"{TABLE_PREFIX}health_event_records"
    
    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="记录ID（ULID）"
    )
    user_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="用户ID"
    )
    event_type = Column(
        String(100),
        nullable=False,
        comment="健康事件类型（如：少吃盐、运动、心情放松、睡眠良好）"
    )
    check_in_time = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="打卡时间（可选，不提供则使用当前时间）"
    )
    notes = Column(
        Text,
        nullable=True,
        comment="备注（可选）"
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
        return (
            f"<HealthEventRecord(id={self.id}, user_id={self.user_id}, "
            f"event_type={self.event_type})>"
        )
