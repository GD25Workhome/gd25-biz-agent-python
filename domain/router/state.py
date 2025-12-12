from typing import TypedDict, Annotated, List, Optional
from langchain_core.messages import BaseMessage
import operator

class RouterState(TypedDict):
    """
    路由状态 (RouterState)
    
    定义了在 Agent 路由过程中传递的状态信息。
    """
    messages: Annotated[List[BaseMessage], operator.add]  # 对话历史消息列表，支持追加
    next_agent: Optional[str]  # 下一个要执行的 Agent 名称
    user_id: Optional[str]  # 用户 ID
    session_id: Optional[str]  # 会话 ID
