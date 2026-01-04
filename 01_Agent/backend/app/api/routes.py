"""
API路由
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage

from backend.app.api.schemas import ChatRequest, ChatResponse
from backend.domain.flows.manager import FlowManager
from backend.domain.state import FlowState

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, app_request: Request) -> ChatResponse:
    """
    聊天接口
    
    Args:
        request: 聊天请求
        app_request: FastAPI请求对象（用于获取应用状态）
        
    Returns:
        ChatResponse: 聊天响应
    """
    try:
        flow_name = request.flow_name or "medical_agent"
        
        # 获取流程图（按需加载）
        graph = FlowManager.get_flow(flow_name)
        
        # 构建初始状态
        initial_state: FlowState = {
            "messages": [HumanMessage(content=request.message)],
            "session_id": request.session_id,
            "intent": None
        }
        
        # 执行流程图
        config = {"configurable": {"thread_id": request.session_id}}
        result = graph.invoke(initial_state, config)
        
        # 提取最后一条AI消息作为回复
        messages = result.get("messages", [])
        if messages:
            last_message = messages[-1]
            response_text = last_message.content if hasattr(last_message, "content") else str(last_message)
        else:
            response_text = "抱歉，我没有收到回复。"
        
        return ChatResponse(
            response=response_text,
            session_id=request.session_id
        )
        
    except Exception as e:
        logger.error(f"处理聊天请求失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}")

