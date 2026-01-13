"""
API层辅助工具方法
提供请求数据转换、状态构建等通用功能
"""
from typing import List, Optional
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from fastapi import HTTPException

from backend.app.api.schemas.chat import ChatRequest, ChatMessage
from backend.domain.state import FlowState
from backend.domain.flows.manager import FlowManager
from backend.domain.context.context_manager import get_context_manager


def build_history_messages(conversation_history: Optional[List[ChatMessage]]) -> List[BaseMessage]:
    """
    从对话历史构建LangChain消息列表
    
    Args:
        conversation_history: 对话历史列表，可能为None
        
    Returns:
        List[BaseMessage]: LangChain消息列表
    """
    history_messages = []
    if conversation_history:
        for msg in conversation_history:
            if msg.role == "user":
                history_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                history_messages.append(AIMessage(content=msg.content))
    return history_messages


def build_current_message(message: str) -> HumanMessage:
    """
    构建当前用户消息
    
    Args:
        message: 用户消息内容
        
    Returns:
        HumanMessage: LangChain HumanMessage对象
    """
    return HumanMessage(content=message)


def build_initial_state(request: ChatRequest, current_message: HumanMessage, 
                       history_messages: List[BaseMessage]) -> FlowState:
    """
    构建流程初始状态
    
    Args:
        request: 聊天请求对象
        current_message: 当前用户消息
        history_messages: 历史消息列表
        
    Returns:
        FlowState: 流程初始状态字典
    """
    return {
        "current_message": current_message,
        "history_messages": history_messages,
        "flow_msgs": [],  # 流程运行中的中间消息（初始化为空列表）
        "session_id": request.session_id,
        "intent": None,
        "token_id": request.token_id,
        "trace_id": request.trace_id,
        "user_info": request.user_info,
        "current_date": request.current_date
    }


def get_flow_graph(session_id: str):
    """
    根据session_id获取流程图
    
    从ContextManager中获取session_context，提取flow_key，然后通过FlowManager获取对应的流程图。
    
    Args:
        session_id: 会话ID
        
    Returns:
        CompiledGraph: 编译后的流程图
        
    Raises:
        HTTPException: 当session不存在或flow_key不存在时抛出异常
    """
    # 获取上下文管理器
    context_manager = get_context_manager()
    
    # 获取session上下文
    session_context = context_manager.get_session_context(session_id)
    if session_context is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session不存在: {session_id}。请先创建Session。"
        )
    
    # 从session_context中提取flow_info
    flow_info = session_context.get("flow_info")
    if flow_info is None:
        raise HTTPException(
            status_code=500,
            detail=f"Session数据格式错误：缺少flow_info。session_id={session_id}"
        )
    
    # 从flow_info中提取flow_key
    flow_key = flow_info.get("flow_key")
    if flow_key is None:
        raise HTTPException(
            status_code=500,
            detail=f"Session数据格式错误：flow_info中缺少flow_key。session_id={session_id}"
        )
    
    # 通过FlowManager获取流程图（按需加载）
    try:
        graph = FlowManager.get_flow(flow_key)
        return graph
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取流程图失败: {str(e)}。flow_key={flow_key}, session_id={session_id}"
        )

