"""
流程状态定义
定义流程执行过程中的状态数据结构
"""
from typing import TypedDict, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage


class FlowState(TypedDict, total=False):
    """
    流程状态数据结构
    
    用于在流程执行过程中传递数据
    """
    current_message: HumanMessage  # 当前用户消息
    history_messages: List[BaseMessage]  # 历史消息列表
    flow_msgs: List[BaseMessage]  # 流程运行中的中间消息（暂存，不参与模型调用）
    session_id: str  # 会话ID
    intent: Optional[str]  # 当前意图（用于路由条件判断）
    confidence: Optional[float]  # 意图识别置信度（0.0-1.0）
    need_clarification: Optional[bool]  # 是否需要澄清意图
    token_id: Optional[str]  # 令牌ID（用于工具参数注入）
    trace_id: Optional[str]  # Trace ID（用于可观测性追踪）
    prompt_vars: Optional[Dict[str, Any]]  # 字典类型，用于存储提示词中的变量

