"""
API请求/响应模型
"""
from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(description="用户消息")
    session_id: str = Field(description="会话ID")
    flow_name: Optional[str] = Field(default="medical_agent", description="流程名称（可选，默认为medical_agent）")


class ChatResponse(BaseModel):
    """聊天响应"""
    response: str = Field(description="助手回复")
    session_id: str = Field(description="会话ID")

