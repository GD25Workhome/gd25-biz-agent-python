"""
血压会话原始记录模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, TABLE_PREFIX, generate_ulid


class BloodPressureSessionRecord(Base):
    """血压会话原始记录模型"""
    
    __tablename__ = f"{TABLE_PREFIX}blood_pressure_session_records"
    
    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="记录ID（ULID）"
    )
    age = Column(
        Integer,
        nullable=True,
        comment="年龄"
    )
    disease = Column(
        String(1000),
        nullable=True,
        comment="疾病"
    )
    blood_pressure = Column(
        String(1000),
        nullable=True,
        comment="血压"
    )
    symptom = Column(
        String(1000),
        nullable=True,
        comment="症状"
    )
    medication = Column(
        String(1000),
        nullable=True,
        comment="用药"
    )
    medication_status = Column(
        String(1000),
        nullable=True,
        comment="用药情况"
    )
    habit = Column(
        String(1000),
        nullable=True,
        comment="习惯"
    )
    history_action = Column(
        String(1000),
        nullable=True,
        comment="历史Action"
    )
    history_session = Column(
        Text,
        nullable=True,
        comment="历史会话"
    )
    history_response = Column(
        Text,
        nullable=True,
        comment="历史会话响应"
    )
    new_session = Column(
        Text,
        nullable=True,
        comment="新会话"
    )
    new_session_response = Column(
        Text,
        nullable=True,
        comment="新会话响应"
    )
    ids = Column(
        String(1000),
        nullable=True,
        comment="ids"
    )
    ext = Column(
        String(1000),
        nullable=True,
        comment="ext"
    )
    source_filename = Column(
        String(200),
        nullable=False,
        index=True,
        comment="来源文件名"
    )
    source_remark1 = Column(
        String(200),
        nullable=False,
        index=True,
        comment="来源备注1"
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
            f"<BloodPressureSessionRecord(id={self.id}, "
            f"source_filename={self.source_filename}, "
            f"source_remark1={self.source_remark1})>"
        )
