"""
LLM 调用日志模型
"""
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    Numeric,
    func,
)

from infrastructure.database.base import Base, generate_ulid


class LlmCallLog(Base):
    """LLM 调用日志主表"""
    
    __tablename__ = "biz_agent_llm_call_logs"
    __allow_unmapped__ = True
    
    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="主键ID"
    )
    call_id = Column(String(64), nullable=False, index=True, comment="调用唯一ID")
    trace_id = Column(String(64), nullable=True, index=True, comment="链路追踪ID")
    session_id = Column(String(64), nullable=True, index=True, comment="会话ID")
    conversation_id = Column(String(64), nullable=True, comment="对话ID")
    user_id = Column(String(50), nullable=True, index=True, comment="用户ID")
    agent_key = Column(String(100), nullable=True, index=True, comment="智能体标识")
    model = Column(String(100), nullable=False, comment="模型名称")
    temperature = Column(Numeric(4, 2), nullable=True, comment="温度参数")
    top_p = Column(Numeric(4, 2), nullable=True, comment="Top-p 参数")
    max_tokens = Column(Integer, nullable=True, comment="最大输出 tokens")
    prompt_tokens = Column(Integer, nullable=True, comment="提示 tokens 消耗")
    completion_tokens = Column(Integer, nullable=True, comment="生成 tokens 消耗")
    total_tokens = Column(Integer, nullable=True, comment="总 tokens 消耗")
    latency_ms = Column(Integer, nullable=True, comment="耗时（毫秒）")
    success = Column(Boolean, default=True, comment="是否成功")
    error_code = Column(String(50), nullable=True, comment="错误码")
    error_message = Column(Text, nullable=True, comment="错误信息")
    prompt_snapshot = Column(Text, nullable=True, comment="提示词快照（截断存储）")
    response_snapshot = Column(Text, nullable=True, comment="响应快照（截断存储）")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="创建时间"
    )
    finished_at = Column(DateTime(timezone=True), nullable=True, comment="完成时间")
    
    # 关系
    def __repr__(self):
        return f"<LlmCallLog(id={self.id}, call_id={self.call_id}, model={self.model})>"


class LlmCallMessage(Base):
    """LLM 调用消息表"""
    
    __tablename__ = "biz_agent_llm_call_messages"
    __allow_unmapped__ = True
    
    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="主键ID"
    )
    call_id = Column(
        String(64),
        nullable=False,
        index=True,
        comment="调用唯一ID"
    )
    role = Column(String(20), nullable=False, comment="角色（system/human/assistant/tool）")
    content = Column(Text, nullable=False, comment="消息内容")
    token_estimate = Column(Integer, nullable=True, comment="token 粗略估算")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="创建时间"
    )
    
    def __repr__(self):
        return f"<LlmCallMessage(id={self.id}, call_id={self.call_id}, role={self.role})>"
