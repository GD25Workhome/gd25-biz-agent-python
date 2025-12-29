"""
用户模型
"""
from uuid import uuid4
from sqlalchemy import Column, String, DateTime, Boolean, Text, func

from infrastructure.database.base import Base


class User(Base):
    """用户模型"""
    
    __tablename__ = "biz_agent_users"
    
    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=lambda: uuid4().hex,
        comment="用户ID"
    )
    username = Column(String(100), nullable=False, comment="用户名")
    phone = Column(String(20), nullable=True, comment="手机号")
    email = Column(String(100), nullable=True, comment="邮箱")
    is_active = Column(Boolean, default=True, comment="是否激活")
    user_info = Column(Text, nullable=True, comment="患者基础信息（多行文本）")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="创建时间"
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
    user_info_updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="患者基础信息更新时间"
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"

