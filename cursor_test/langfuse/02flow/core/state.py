"""
流程状态定义
定义流程执行过程中的状态数据结构
"""
from typing import TypedDict, List, Optional
from langchain_core.messages import BaseMessage


class FlowState(TypedDict, total=False):
    """
    流程状态数据结构
    
    用于在流程执行过程中传递数据
    """
    messages: List[BaseMessage]  # 消息列表
    session_id: str  # 会话ID
    intent: Optional[str]  # 当前意图（用于路由条件判断）
    next: Optional[str]  # 下一个节点名称（用于supervisor节点路由决策）
    token_id: Optional[str]  # 令牌ID（用于工具参数注入）
    trace_id: Optional[str]  # Trace ID（用于可观测性追踪）
    user_info: Optional[str]  # 患者基础信息（多行文本）
    current_date: Optional[str]  # 当前日期时间（格式：YYYY-MM-DD HH:mm）
    # 可以根据需要扩展其他字段

