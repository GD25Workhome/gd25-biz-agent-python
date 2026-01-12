"""
聊天相关路由
"""
import logging
import secrets
from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage, AIMessage

from backend.app.api.schemas.chat import ChatRequest, ChatResponse
from backend.app.api.decorators import validate_context_cache
from backend.domain.flows.manager import FlowManager
from backend.domain.state import FlowState
from backend.domain.tools.context import TokenContext
from backend.domain.context.context_manager import get_context_manager
from backend.infrastructure.observability.langfuse_handler import (
    set_langfuse_trace_context,
    create_langfuse_handler
)
import json

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
@validate_context_cache
async def chat(
    request: ChatRequest,
    app_request: Request
) -> ChatResponse:
    """
    聊天接口
    
    Args:
        request: 聊天请求
        app_request: FastAPI请求对象（用于获取应用状态）
        
    Returns:
        ChatResponse: 聊天响应
    """
    try:
        
        # # 设置Langfuse Trace上下文
        # langfuse_trace_id = set_langfuse_trace_context(
        #     # name="chat_request",
        #     name = request.flow_name or "UnknownChat",
        #     user_id=request.token_id,
        #     session_id=request.session_id,
        #     trace_id=trace_id,
        #     metadata={
        #         "message_length": len(request.message),
        #         "history_count": len(request.conversation_history) if request.conversation_history else 0,
        #         "flow_name": request.flow_name or "medical_agent",
        #     }
        # )
        
        # 记录请求开始
        logger.info(
            f"[Chat请求开始] session_id={request.session_id}, "
            f"token_id={request.token_id}, "
            f"trace_id={request.trace_id}, "
            f"message_length={len(request.message)}, "
            f"history_count={len(request.conversation_history) if request.conversation_history else 0}"
        )
        
        flow_name = request.flow_name or "medical_agent"
        
        # 获取流程图（按需加载）
        graph = FlowManager.get_flow(flow_name)
        
        # 构建历史消息列表（从conversation_history）
        history_messages = []
        if request.conversation_history:
            for msg in request.conversation_history:
                if msg.role == "user":
                    history_messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    history_messages.append(AIMessage(content=msg.content))
        
        # 构建当前用户消息
        current_message = HumanMessage(content=request.message)
        
        # 获取上下文管理器
        context_manager = get_context_manager()
        
        # # 创建或获取聊天上下文
        # session_context = context_manager.get_or_create_session_context(session_id=request.session_id)
        
        # # 创建或获取Token上下文
        # token_context = context_manager.get_or_create_token_context(token_id=request.token_id)
        
        # # 创建或获取用户信息（从Token ID获取或创建）
        # user_info = context_manager.get_or_create_user_info(user_id=request.token_id)
        
        # # 初始化用户信息（从请求中加载用户信息）
        # if request.user_info:
        #     try:
        #         # 尝试解析user_info为JSON
        #         if isinstance(request.user_info, str):
        #             user_info_dict = json.loads(request.user_info)
        #         else:
        #             user_info_dict = request.user_info
        #         user_info.set_user_info(user_info_dict)
        #     except (json.JSONDecodeError, TypeError):
        #         # 如果解析失败，作为字符串存储
        #         token_context["user_info_raw"] = request.user_info
        
        # # 将上下文数据添加到聊天上下文（用于提示词替换）
        # session_context["current_date"] = request.current_date
        # session_context["user_info"] = user_info.get_user_info()
        
        # 构建初始状态
        initial_state: FlowState = {
            "current_message": current_message,
            "history_messages": history_messages,
            "session_id": request.session_id,
            "intent": None,
            "token_id": request.token_id,
            "trace_id": request.trace_id,
            "user_info": request.user_info,
            "current_date": request.current_date
        }
        
        # 创建Langfuse CallbackHandler（用于在LLM调用时自动记录到Langfuse）
        langfuse_handler = create_langfuse_handler(context={"trace_id": request.trace_id})
        
        # 在TokenContext中执行流程图（确保工具可以获取token_id）
        with TokenContext(token_id=request.token_id):
            # 构建配置（包含callbacks）
            config = {"configurable": {"thread_id": request.session_id}}
            if langfuse_handler:
                config["callbacks"] = [langfuse_handler]
            
            # 执行流程图
            result = graph.invoke(initial_state, config)
        
        # 提取最后一条AI消息作为回复
        # 合并历史消息和当前消息（如果存在），查找最后一条AI消息
        history_messages = result.get("history_messages", [])
        current_message = result.get("current_message")
        all_messages = history_messages.copy()
        if current_message:
            all_messages.append(current_message)
        
        # 从后往前查找最后一条AI消息
        ai_messages = [msg for msg in all_messages if isinstance(msg, AIMessage)]
        if ai_messages:
            last_message = ai_messages[-1]
            response_text = last_message.content if hasattr(last_message, "content") else str(last_message)
        else:
            response_text = "抱歉，我没有收到回复。"
        
        logger.info(
            f"[Chat请求完成] session_id={request.session_id}, "
            f"response_length={len(response_text)}"
        )
        
        return ChatResponse(
            response=response_text,
            session_id=request.session_id
        )
        
    except Exception as e:
        logger.error(f"处理聊天请求失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}")

