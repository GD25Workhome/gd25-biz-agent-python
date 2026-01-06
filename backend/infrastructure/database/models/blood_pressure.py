"""
血压记录模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, func
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, TABLE_PREFIX, generate_ulid


class BloodPressureRecord(Base):
    """血压记录模型"""
    
    __tablename__ = f"{TABLE_PREFIX}blood_pressure_records"
    
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
    systolic = Column(
        Integer,
        nullable=False,
        comment="收缩压（高压，单位：mmHg）"
    )
    diastolic = Column(
        Integer,
        nullable=False,
        comment="舒张压（低压，单位：mmHg）"
    )
    heart_rate = Column(
        Integer,
        nullable=True,
        comment="心率（单位：bpm，可选）"
    )
    record_time = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="记录时间（可选）"
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
            f"<BloodPressureRecord(id={self.id}, user_id={self.user_id}, "
            f"systolic={self.systolic}, diastolic={self.diastolic})>"
        )

