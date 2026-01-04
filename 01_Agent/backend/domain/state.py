"""
流程状态定义
定义流程执行过程中的状态数据结构
"""
from typing import TypedDict, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage


class FlowState(TypedDict, total=False):
    """
    流程状态数据结构
    
    用于在流程执行过程中传递数据
    """
    messages: List[BaseMessage]  # 消息列表
    session_id: str  # 会话ID
    intent: Optional[str]  # 当前意图（用于路由条件判断）
    # 可以根据需要扩展其他字段

