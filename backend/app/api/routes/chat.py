"""
聊天相关 HTTP 路由

提供 /chat 接口：组装会话上下文、执行 LangGraph 流程并返回 AI 回复。
"""
import json
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
    get_flow_graph,
)
from backend.domain.tools.context import RuntimeContext
from backend.infrastructure.observability.langfuse_handler import (
    set_langfuse_trace_context,
    create_langfuse_handler,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
@validate_context_cache
async def chat(
    request: ChatRequest,
    app_request: Request,
) -> ChatResponse:
    """
        处理用户聊天请求：加载流程图、执行 LangGraph 并返回 AI 回复文本。

        Args:
            request: 聊天请求体（session、消息、历史等）
            app_request: FastAPI 请求对象（装饰器与中间件可能使用）

        Returns:
            ChatResponse: 含 AI 回复与会话 ID

        Raises:
            HTTPException: 流程执行或回复解析失败时返回 500
    """
    try:
        # 1. 记录请求审计日志
        logger.info(
            f"[Chat请求开始]》〉》〉》〉》〉》〉》〉》〉》〉》〉》〉》〉》〉》〉》〉》〉》 session_id={request.session_id}, "
            f"token_id={request.token_id}, "
            f"trace_id={request.trace_id}, "
            f"message_length={len(request.message)}, "
            f"history_count={len(request.conversation_history) if request.conversation_history else 0}"
        )

        # 2. 根据 session 获取流程图及 flow 元信息
        # get_flow_graph：从 Session 解析 flow_key，经 FlowManager 取编译图（预加载或按需加载）
        graph, flow_key, flow_name = get_flow_graph(request.session_id)

        # 3~4. 组装 LangChain 消息并构建 Flow 初始状态
        history_messages = build_history_messages(request.conversation_history)
        current_message = build_current_message(request.message)
        initial_state = build_initial_state(request, current_message, history_messages)

        # 5. 创建 Langfuse 回调，供 LLM 调用链路自动上报可观测数据
        langfuse_handler = create_langfuse_handler(context={"trace_id": request.trace_id})

        # 6. 在 RuntimeContext 下异步执行流程图
        with RuntimeContext(
            token_id=request.token_id,
            session_id=request.session_id,
            trace_id=request.trace_id,
        ):
            config = {"configurable": {"thread_id": request.session_id}}
            if langfuse_handler:
                config["callbacks"] = [langfuse_handler]
                config["metadata"] = {
                    "langfuse_user_id": request.token_id or "",
                    "langfuse_session_id": request.session_id,
                    "langfuse_tags": ["chat", "api"],
                    "flow_key": flow_key,
                    "flow_name": flow_name,
                    "source": "chat_api",
                    "message_length": str(len(request.message)),
                    "history_count": str(len(request.conversation_history or [])),
                }

            # graph.ainvoke：按 initial_state 驱动 LangGraph 全链路执行
            result = await graph.ainvoke(initial_state, config)

        # 7. 从 flow_msgs 提取最后一条 AI 消息，并尝试解析 JSON 中的 response_content
        flow_msgs = result.get("flow_msgs", [])
        ai_messages = [msg for msg in flow_msgs if isinstance(msg, AIMessage)]
        if ai_messages:
            last_message = ai_messages[-1]
            raw_content = last_message.content if hasattr(last_message, "content") else str(last_message)

            response_text = raw_content
            try:
                parsed_content = json.loads(raw_content)
                if isinstance(parsed_content, dict) and "response_content" in parsed_content:
                    response_content_value = parsed_content.get("response_content")
                    if response_content_value is not None and str(response_content_value).strip():
                        response_text = str(response_content_value)
            except (json.JSONDecodeError, TypeError, AttributeError):
                # 非 JSON 或字段缺失时保留原始字符串
                pass
        else:
            response_text = "抱歉，我没有收到回复。"

        # 8. 返回结构化响应
        logger.info(
            f"[Chat请求完成] session_id={request.session_id}, "
            f"response_length={len(response_text)}"
        )
        return ChatResponse(
            response=response_text,
            session_id=request.session_id,
        )

    except Exception as e:
        logger.error(f"处理聊天请求失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}")
