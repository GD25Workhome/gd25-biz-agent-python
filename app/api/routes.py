"""
API 路由定义
"""
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.schemas.chat import ChatRequest, ChatResponse
from domain.router.state import RouterState

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    app_request: Request
) -> ChatResponse:
    """
    聊天接口
    
    Args:
        request: 聊天请求
        app_request: FastAPI 请求对象（用于获取应用状态）
        
    Returns:
        聊天响应
    """
    # 获取路由图
    router_graph = app_request.app.state.router_graph
    checkpointer = app_request.app.state.checkpointer
    
    if not router_graph:
        raise HTTPException(status_code=500, detail="路由图未初始化")
    
    # 构建消息列表
    messages = []
    if request.conversation_history:
        for msg in request.conversation_history:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))
    
    # 添加当前用户消息
    messages.append(HumanMessage(content=request.message))
    
    # 构建初始状态
    initial_state: RouterState = {
        "messages": messages,
        "current_intent": None,
        "current_agent": None,
        "need_reroute": True,
        "session_id": request.session_id,
        "user_id": request.user_id
    }
    
    # 配置（包含 checkpointer）
    # 注意：checkpointer 应该在编译图时传入，而不是在运行时配置
    config: Dict[str, Any] = {
        "configurable": {
            "thread_id": request.session_id
        }
    }
    
    # 执行路由图
    try:
        result = None
        async for event in router_graph.astream(initial_state, config=config):
            # 获取最后一个节点的输出
            for node_name, node_output in event.items():
                result = node_output
        
        if not result:
            raise HTTPException(status_code=500, detail="路由图执行失败")
        
        # 获取最后一条助手消息
        response_message = None
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage):
                response_message = msg
                break
        
        if not response_message:
            response_message = "抱歉，我无法理解您的问题。"
        else:
            response_message = response_message.content
        
        return ChatResponse(
            response=response_message,
            session_id=request.session_id,
            intent=result.get("current_intent"),
            agent=result.get("current_agent")
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理请求时出错: {str(e)}")

