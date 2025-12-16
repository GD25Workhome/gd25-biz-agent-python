"""
用户模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship

from infrastructure.database.base import Base


class User(Base):
    """用户模型"""
    
    __tablename__ = "biz_agent_users"
    
    id = Column(Integer, primary_key=True, index=True, comment="用户ID")
    username = Column(String(100), unique=True, index=True, nullable=False, comment="用户名")
    phone = Column(String(20), unique=True, index=True, nullable=True, comment="手机号")
    email = Column(String(100), unique=True, index=True, nullable=True, comment="邮箱")
    is_active = Column(Boolean, default=True, comment="是否激活")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关系
    blood_pressure_records = relationship("BloodPressureRecord", back_populates="user", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"

