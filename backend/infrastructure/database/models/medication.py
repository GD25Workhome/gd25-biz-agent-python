"""
药品记录模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, TABLE_PREFIX, generate_ulid


class MedicationRecord(Base):
    """药品记录模型"""
    
    __tablename__ = f"{TABLE_PREFIX}medication_records"
    
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
    medication_name = Column(
        String(200),
        nullable=False,
        comment="药品名称（冗余字段，便于查询和显示）"
    )
    medication_time = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="用药时间（可选，不提供则使用当前时间）"
    )
    dosage = Column(
        Integer,
        nullable=False,
        comment="每次服用剂量（如：2）"
    )
    dosage_unit = Column(
        String(50),
        nullable=False,
        comment="剂量单位（如：片、粒、ml、mg等）"
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
            f"<MedicationRecord(id={self.id}, user_id={self.user_id}, "
            f"medication_name={self.medication_name}, dosage={self.dosage}{self.dosage_unit})>"
        )
