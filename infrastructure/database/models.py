from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from infrastructure.database.base import Base

class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # 关系定义
    blood_pressure_records: Mapped[List["BloodPressureRecord"]] = relationship(back_populates="user")
    appointments: Mapped[List["Appointment"]] = relationship(back_populates="user")

class BloodPressureRecord(Base):
    """血压记录表"""
    __tablename__ = "blood_pressure_records"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    systolic: Mapped[int] = mapped_column(Integer)  # 收缩压
    diastolic: Mapped[int] = mapped_column(Integer) # 舒张压
    heart_rate: Mapped[int] = mapped_column(Integer) # 心率
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    user: Mapped["User"] = relationship(back_populates="blood_pressure_records")

class Appointment(Base):
    """预约记录表"""
    __tablename__ = "appointments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    doctor_name: Mapped[str] = mapped_column(String(100))
    department: Mapped[str] = mapped_column(String(100))
    appointment_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="scheduled") # scheduled(已预约), completed(已完成), cancelled(已取消)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    user: Mapped["User"] = relationship(back_populates="appointments")

class KnowledgeBase(Base):
    """RAG 知识库表"""
    __tablename__ = "knowledge_base"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    content: Mapped[str] = mapped_column(Text)
    # 使用 m3e-base (768 dims) 或 OpenAI (1536 dims)
    # 注意: 如果修改此维度，需要进行数据库迁移 (Alembic)
    embedding: Mapped[Vector] = mapped_column(Vector(768)) 
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})
    source: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ChatHistory(Base):
    """对话历史表 (业务层)"""
    __tablename__ = "chat_history"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    role: Mapped[str] = mapped_column(String(20)) # user(用户), assistant(助手), system(系统)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AgentTrace(Base):
    """Agent 执行链路追踪表"""
    __tablename__ = "agent_traces"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    step_name: Mapped[str] = mapped_column(String(100))
    inputs: Mapped[Dict[str, Any]] = mapped_column(JSON)
    outputs: Mapped[Dict[str, Any]] = mapped_column(JSON)
    execution_time: Mapped[float] = mapped_column(Integer, comment="执行时间（毫秒）") 
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
