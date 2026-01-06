"""
聊天相关路由
"""
import logging
import secrets
from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage, AIMessage

from backend.app.api.schemas.chat import ChatRequest, ChatResponse
from backend.domain.flows.manager import FlowManager
from backend.domain.state import FlowState
from backend.domain.tools.context import TokenContext
from backend.domain.context.manager import get_context_manager
from backend.infrastructure.observability.langfuse_handler import set_langfuse_trace_context
import json

logger = logging.getLogger(__name__)
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
        app_request: FastAPI请求对象（用于获取应用状态）
        
    Returns:
        ChatResponse: 聊天响应
    """
    try:
        # 获取或生成 traceId（32位小写十六进制字符，符合Langfuse格式要求）
        trace_id = request.trace_id
        if not trace_id:
            # 使用 secrets.token_hex(16) 生成32位十六进制字符（16字节 = 32个十六进制字符）
            trace_id = secrets.token_hex(16)
        
        # 设置Langfuse Trace上下文
        langfuse_trace_id = set_langfuse_trace_context(
            # name="chat_request",
            name = request.flow_name or "UnknownChat",
            user_id=request.token_id,
            session_id=request.session_id,
            trace_id=trace_id,
            metadata={
                "message_length": len(request.message),
                "history_count": len(request.conversation_history) if request.conversation_history else 0,
                "flow_name": request.flow_name or "medical_agent",
            }
        )
        
        # 如果Langfuse创建了Trace，使用Langfuse的Trace ID
        if langfuse_trace_id:
            trace_id = langfuse_trace_id
        
        # 记录请求开始
        logger.info(
            f"[Chat请求开始] session_id={request.session_id}, "
            f"token_id={request.token_id}, "
            f"trace_id={trace_id}, "
            f"message_length={len(request.message)}, "
            f"history_count={len(request.conversation_history) if request.conversation_history else 0}"
        )
        
        flow_name = request.flow_name or "medical_agent"
        
        # 获取流程图（按需加载）
        graph = FlowManager.get_flow(flow_name)
        
        # 构建消息列表（从conversation_history和当前消息）
        messages = []
        if request.conversation_history:
            for msg in request.conversation_history:
                if msg.role == "user":
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    messages.append(AIMessage(content=msg.content))
        
        # 添加当前用户消息
        messages.append(HumanMessage(content=request.message))
        
        # 获取上下文管理器
        context_manager = get_context_manager()
        
        # 创建或获取流程上下文
        flow_context = context_manager.get_or_create_flow_context(flow_id=request.session_id)
        
        # 创建或获取用户上下文
        user_context = context_manager.get_or_create_user_context(user_id=request.token_id)
        
        # 初始化用户上下文（从请求中加载用户信息）
        if request.user_info:
            try:
                # 尝试解析user_info为JSON
                if isinstance(request.user_info, str):
                    user_info_dict = json.loads(request.user_info)
                else:
                    user_info_dict = request.user_info
                user_context.set_user_info(user_info_dict)
            except (json.JSONDecodeError, TypeError):
                # 如果解析失败，作为字符串存储
                user_context.set("user_info_raw", request.user_info)
        
        # 将上下文数据添加到流程上下文（用于提示词替换）
        flow_context.set("current_date", request.current_date)
        flow_context.set("user_info", user_context.get_user_info())
        
        # 构建初始状态
        initial_state: FlowState = {
            "messages": messages,
            "session_id": request.session_id,
            "intent": None,
            "token_id": request.token_id,
            "trace_id": trace_id,
            "user_info": request.user_info,
            "current_date": request.current_date
        }
        
        # 在TokenContext中执行流程图（确保工具可以获取token_id）
        with TokenContext(token_id=request.token_id):
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

