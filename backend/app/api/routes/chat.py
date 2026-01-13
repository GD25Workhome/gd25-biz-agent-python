"""
聊天相关路由
"""
import logging
import secrets
from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage, AIMessage

from backend.app.api.schemas.chat import ChatRequest, ChatResponse
from backend.app.api.decorators import validate_context_cache
from backend.app.api.helpers import (
    build_history_messages,
    build_current_message,
    build_initial_state,
    get_flow_graph
)
from backend.domain.tools.context import RuntimeContext
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
        # 记录请求开始
        logger.info(
            f"[Chat请求开始]》〉》〉》〉》〉》〉》〉》〉》〉》〉》〉》〉》〉》〉》〉》〉》 session_id={request.session_id}, "
            f"token_id={request.token_id}, "
            f"trace_id={request.trace_id}, "
            f"message_length={len(request.message)}, "
            f"history_count={len(request.conversation_history) if request.conversation_history else 0}"
        )
        
        # 获取流程图（按需加载）
        graph = get_flow_graph(request.session_id)
        
        # 构建历史消息列表（从conversation_history）
        history_messages = build_history_messages(request.conversation_history)
        
        # 构建当前用户消息
        current_message = build_current_message(request.message)
        
        # 构建初始状态
        initial_state = build_initial_state(request, current_message, history_messages)
        
        # 创建Langfuse CallbackHandler（用于在LLM调用时自动记录到Langfuse）
        langfuse_handler = create_langfuse_handler(context={"trace_id": request.trace_id})
        
        # 在RuntimeContext中执行流程图（确保工具可以获取运行时信息）
        with RuntimeContext(
            token_id=request.token_id,
            session_id=request.session_id,
            trace_id=request.trace_id
        ):
            # 构建配置（包含callbacks）
            config = {"configurable": {"thread_id": request.session_id}}
            if langfuse_handler:
                config["callbacks"] = [langfuse_handler]
            
            # 执行流程图
            result = await graph.ainvoke(initial_state, config)
        
        # 提取最后一条AI消息作为回复
        # 从 flow_msgs 中提取最后一条 AI 消息（流程中间消息）
        flow_msgs = result.get("flow_msgs", [])
        
        # 从后往前查找最后一条AI消息
        ai_messages = [msg for msg in flow_msgs if isinstance(msg, AIMessage)]
        if ai_messages:
            last_message = ai_messages[-1]
            raw_content = last_message.content if hasattr(last_message, "content") else str(last_message)
            
            # 尝试解析为 JSON 对象，提取 response_content
            response_text = raw_content
            try:
                # 尝试解析为 JSON
                parsed_content = json.loads(raw_content)
                # 如果是字典类型，尝试读取 response_content
                if isinstance(parsed_content, dict) and "response_content" in parsed_content:
                    response_content_value = parsed_content.get("response_content")
                    # 如果 response_content 存在且不为空，则使用它
                    if response_content_value is not None and str(response_content_value).strip():
                        response_text = str(response_content_value)
            except (json.JSONDecodeError, TypeError, AttributeError):
                # 解析失败或不是 JSON 格式，使用原始字符串
                pass
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

