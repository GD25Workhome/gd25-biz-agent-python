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
    token_id: Optional[str]  # 令牌ID（用于工具参数注入）
    trace_id: Optional[str]  # Trace ID（用于可观测性追踪）
    prompt_vars: Optional[Dict[str, Any]]  # 字典类型，用于存储提示词中的变量
    edges_var: Optional[Dict[str, Any]]  # 边条件判断变量存储（通用化设计）
    persistence_edges_var: Optional[Dict[str, Any]]  # 持久化边变量通道，透传到任意下级节点，边条件合并时 edges_var 优先

