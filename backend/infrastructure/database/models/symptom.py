"""
症状信息模型
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, TABLE_PREFIX, generate_ulid


class SymptomRecord(Base):
    """症状信息模型"""
    
    __tablename__ = f"{TABLE_PREFIX}symptom_records"
    
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
    symptom_name = Column(
        String(200),
        nullable=False,
        comment="症状名"
    )
    record_time = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="症状记录时间（可选，不提供则使用当前时间）"
    )
    recovery_status = Column(
        String(20),
        nullable=False,
        comment="是否已经痊愈（枚举：新记录、老记录、痊愈）"
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
            f"<SymptomRecord(id={self.id}, user_id={self.user_id}, "
            f"symptom_name={self.symptom_name}, recovery_status={self.recovery_status})>"
        )
