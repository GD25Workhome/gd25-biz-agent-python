from pydantic import BaseModel
from typing import Optional, List, Any

class ChatRequest(BaseModel):
    """
    聊天请求模型
    """
    message: str  # 用户发送的消息内容
    session_id: str  # 会话 ID
    user_id: str  # 用户 ID

class ChatResponse(BaseModel):
    """
    聊天响应模型
    """
    response: str  # 系统回复的内容
    metadata: Optional[dict] = None  # 元数据
