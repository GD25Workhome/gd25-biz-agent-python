"""
血压记录模型
"""
from uuid import uuid4
from sqlalchemy import Column, Integer, String, DateTime, Text, func

from infrastructure.database.base import Base


class BloodPressureRecord(Base):
    """血压记录模型"""
    
    __tablename__ = "biz_agent_blood_pressure_records"
    
    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=lambda: uuid4().hex,
        comment="记录ID"
    )
    user_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="用户ID"
    )
    systolic = Column(Integer, nullable=False, comment="收缩压（高压）")
    diastolic = Column(Integer, nullable=False, comment="舒张压（低压）")
    heart_rate = Column(Integer, nullable=True, comment="心率")
    record_time = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="记录时间（可为空，默认NULL）"
    )
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
        return f"<BloodPressureRecord(id={self.id}, user_id={self.user_id}, systolic={self.systolic}, diastolic={self.diastolic})>"

