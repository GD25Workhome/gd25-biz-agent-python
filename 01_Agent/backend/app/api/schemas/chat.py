"""
聊天相关Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class ChatMessage(BaseModel):
    """聊天消息模型"""
    role: str = Field(..., description="消息角色：user, assistant, system")
    content: str = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., description="用户消息")
    session_id: str = Field(..., description="会话ID")
    token_id: str = Field(..., description="令牌ID（当前阶段等于用户ID，未来可扩展为业务系统令牌）")
    flow_name: Optional[str] = Field(default="medical_agent", description="流程名称（可选，默认为medical_agent）")
    conversation_history: Optional[List[ChatMessage]] = Field(
        default=None,
        description="对话历史（可选）"
    )
    user_info: Optional[str] = Field(default=None, description="患者基础信息（多行文本）")
    current_date: Optional[str] = Field(
        default=None, 
        description="当前日期时间（格式：YYYY-MM-DD HH:mm，可选，如果不提供则使用系统当前时间）"
    )
    trace_id: Optional[str] = Field(
        default=None,
        description="Trace ID（可选，32位小写十六进制字符，如果未提供则自动生成）"
    )


class ChatResponse(BaseModel):
    """聊天响应"""
    response: str = Field(description="助手回复")
    session_id: str = Field(description="会话ID")

