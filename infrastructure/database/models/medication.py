"""
用药记录模型
"""
from uuid import uuid4
from sqlalchemy import Column, String, DateTime, Text, func

from infrastructure.database.base import Base


class MedicationRecord(Base):
    """用药记录模型"""
    
    __tablename__ = "biz_agent_medication_records"
    
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
    medication_name = Column(
        String(200),
        nullable=False,
        comment="药物名称"
    )
    dosage = Column(
        String(100),
        nullable=False,
        comment="剂量（如：10mg、1片等）"
    )
    frequency = Column(
        String(100),
        nullable=False,
        comment="用药频率（如：每日一次、每日三次等）"
    )
    start_date = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="开始日期（可为空，默认NULL）"
    )
    end_date = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="结束日期（可为空，默认NULL）"
    )
    doctor_name = Column(
        String(100),
        nullable=True,
        comment="开药医生"
    )
    purpose = Column(
        String(200),
        nullable=True,
        comment="用药目的（如：降血压、治疗感冒等）"
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
        return f"<MedicationRecord(id={self.id}, user_id={self.user_id}, medication_name={self.medication_name})>"
