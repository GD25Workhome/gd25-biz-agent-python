"""
预约模型
"""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import Column, String, DateTime, Text, Enum as SQLEnum
import enum

from infrastructure.database.base import Base


class AppointmentStatus(str, enum.Enum):
    """预约状态枚举"""
    PENDING = "pending"  # 待确认
    CONFIRMED = "confirmed"  # 已确认
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


class Appointment(Base):
    """预约模型"""
    
    __tablename__ = "biz_agent_appointments"
    
    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=lambda: uuid4().hex,
        comment="预约ID"
    )
    user_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="用户ID"
    )
    department = Column(String(100), nullable=False, comment="科室")
    doctor_name = Column(String(100), nullable=True, comment="医生姓名")
    appointment_time = Column(DateTime, nullable=False, index=True, comment="预约时间")
    status = Column(SQLEnum(AppointmentStatus), default=AppointmentStatus.PENDING, comment="预约状态")
    notes = Column(Text, nullable=True, comment="备注")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    def __repr__(self):
        return f"<Appointment(id={self.id}, user_id={self.user_id}, department={self.department}, appointment_time={self.appointment_time})>"

