"""
症状记录模型
"""
from sqlalchemy import Column, String, DateTime, Text, func

from infrastructure.database.base import Base, generate_ulid


class SymptomRecord(Base):
    """症状记录模型"""
    
    __tablename__ = "biz_agent_symptom_records"
    
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
    symptom_name = Column(
        String(200),
        nullable=False,
        comment="症状名称（如：头痛、发热、咳嗽等）"
    )
    severity = Column(
        String(50),
        nullable=True,
        comment="严重程度（如：轻微、中等、严重）"
    )
    start_time = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="开始时间（可为空，默认NULL）"
    )
    end_time = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="结束时间（可为空，默认NULL）"
    )
    duration = Column(
        String(100),
        nullable=True,
        comment="持续时间（如：2小时、3天等）"
    )
    location = Column(
        String(200),
        nullable=True,
        comment="症状部位（如：头部、胸部等）"
    )
    description = Column(Text, nullable=True, comment="症状描述")
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
        return f"<SymptomRecord(id={self.id}, user_id={self.user_id}, symptom_name={self.symptom_name})>"
