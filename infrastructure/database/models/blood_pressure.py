"""
血压记录模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from infrastructure.database.base import Base


class BloodPressureRecord(Base):
    """血压记录模型"""
    
    __tablename__ = "biz_agent_blood_pressure_records"
    
    id = Column(Integer, primary_key=True, index=True, comment="记录ID")
    user_id = Column(Integer, ForeignKey("biz_agent_users.id"), nullable=False, index=True, comment="用户ID")
    systolic = Column(Integer, nullable=False, comment="收缩压（高压）")
    diastolic = Column(Integer, nullable=False, comment="舒张压（低压）")
    heart_rate = Column(Integer, nullable=True, comment="心率")
    record_time = Column(DateTime, nullable=False, index=True, comment="记录时间")
    notes = Column(Text, nullable=True, comment="备注")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关系
    user = relationship("User", back_populates="blood_pressure_records")
    
    def __repr__(self):
        return f"<BloodPressureRecord(id={self.id}, user_id={self.user_id}, systolic={self.systolic}, diastolic={self.diastolic})>"

