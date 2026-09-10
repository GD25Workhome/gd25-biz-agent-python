"""
华院联通聊天路由

无 Session / Token 校验的轻量对话接口，固定绑定 huayuan_simple_agent 流程。
"""
import logging
import secrets
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage, HumanMessage

from backend.app.api.schemas.huayuan_chat import HuayuanChatRequest, HuayuanChatResponse
from backend.domain.flows.manager import FlowManager
from backend.domain.state import FlowState
from backend.infrastructure.observability.langfuse_handler import create_langfuse_handler

logger = logging.getLogger(__name__)
router = APIRouter()

# 本接口固定使用的流程 key，与 config/flows/huayuan_simple_agent 对应
HUAYUAN_FLOW_KEY = "huayuan_simple_agent"


def build_huayuan_initial_state(query: str, trace_id: str) -> FlowState:
    """
        构造华院联通流程的最小初始状态（不读取 ContextManager）。

        Args:
            query: 用户本轮输入
            trace_id: 本次请求的 Trace ID

        Returns:
            可供 flowchart ainvoke 的 FlowState
    """
    return {
        "current_message": HumanMessage(content=query),
        "history_messages": [],
        "flow_msgs": [],
        "session_id": "",
        "token_id": "",
        "trace_id": trace_id,
        "prompt_vars": {
            "current_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def extract_response_text(result: Dict[str, Any]) -> str:
    """
        从流程执行结果中提取助手回复文本。

        Args:
            result: graph.ainvoke 返回的状态字典

        Returns:
            最后一条 AIMessage 的 content；若无则返回兜底文案
    """
    flow_msgs = result.get("flow_msgs", []) or []
    ai_messages = [msg for msg in flow_msgs if isinstance(msg, AIMessage)]
    if not ai_messages:
        return "抱歉，我没有收到回复。"

    last_message = ai_messages[-1]
    raw_content = last_message.content if hasattr(last_message, "content") else str(last_message)
    if raw_content is None:
        return "抱歉，我没有收到回复。"
    text = str(raw_content).strip()
    return text if text else "抱歉，我没有收到回复。"


@router.post("/huayuan/chat", response_model=HuayuanChatResponse)
async def huayuan_chat(request: HuayuanChatRequest) -> HuayuanChatResponse:
    """
        华院联通聊天接口：根据用户 query 调用单节点流程并返回回复。

        Args:
            request: 华院联通聊天请求

        Returns:
            含 response 与 trace_id 的响应

        Raises:
            HTTPException: 流程加载或执行失败时返回 500
    """
    # 1. 解析或生成 trace_id
    trace_id = request.trace_id or secrets.token_hex(16)

    logger.info(
        f"[华院Chat请求开始] trace_id={trace_id}, query_length={len(request.query)}"
    )

    try:
        # 2. 加载固定流程
        # FlowManager.get_flow：按需编译并返回流程图
        graph = FlowManager.get_flow(HUAYUAN_FLOW_KEY)

        # 3. 构造最小初始状态并执行
        initial_state = build_huayuan_initial_state(request.query, trace_id)
        # create_langfuse_handler：可选可观测性回调，不可用时返回 None
        langfuse_handler = create_langfuse_handler(context={"trace_id": trace_id})

        config: Dict[str, Any] = {
            "configurable": {"thread_id": f"huayuan_{trace_id}"},
        }
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]
            config["metadata"] = {
                "langfuse_tags": ["huayuan_chat", "api"],
                "flow_key": HUAYUAN_FLOW_KEY,
                "source": "huayuan_chat_api",
                "query_length": str(len(request.query)),
            }

        result = await graph.ainvoke(initial_state, config)

        # 4. 提取回复并返回
        response_text = extract_response_text(result)
        logger.info(
            f"[华院Chat请求完成] trace_id={trace_id}, response_length={len(response_text)}"
        )
        return HuayuanChatResponse(response=response_text, trace_id=trace_id)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"华院Chat流程加载失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"流程加载失败: {str(e)}") from e
    except Exception as e:
        logger.error(f"处理华院Chat请求失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}") from e
