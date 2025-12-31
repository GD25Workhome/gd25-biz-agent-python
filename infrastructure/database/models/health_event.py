"""
健康事件记录模型
"""
from sqlalchemy import Column, String, DateTime, Text, func

from infrastructure.database.base import Base, generate_ulid


class HealthEventRecord(Base):
    """健康事件记录模型"""
    
    __tablename__ = "biz_agent_health_event_records"
    
    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="记录ID"
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
        comment="事件类型（如：体检、检查、手术、疫苗接种等）"
    )
    event_name = Column(
        String(200),
        nullable=False,
        comment="事件名称（如：年度体检、血常规检查等）"
    )
    event_date = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="事件日期（可为空，默认NULL）"
    )
    location = Column(
        String(200),
        nullable=True,
        comment="发生地点（如：医院名称）"
    )
    description = Column(Text, nullable=True, comment="事件描述")
    notes = Column(Text, nullable=True, comment="备注")
    created_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="创建时间（可为空，默认NULL）"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
        comment="更新时间（可为空，默认NULL）"
    )
    
    def __repr__(self):
        return f"<HealthEventRecord(id={self.id}, user_id={self.user_id}, event_type={self.event_type}, event_name={self.event_name})>"
