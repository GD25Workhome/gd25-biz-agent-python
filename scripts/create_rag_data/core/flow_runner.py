"""
封装：组装 state（含 scene_record_content）→ graph.ainvoke → 从 state 取模型回复文本。
"""
import logging
from typing import Any

from langchain_core.messages import HumanMessage

from backend.domain.state import FlowState

logger = logging.getLogger(__name__)

# 脚本占位 token_id / session_id 前缀（无真实用户时使用）
TOKEN_ID_PLACEHOLDER: str = "create_rag_data"
SESSION_ID_PREFIX: str = "create_rag_data_"


def build_initial_state(scene_record_content: str, file_id: str = "") -> FlowState:
    """
    组装单节点 flow 的初始 state。

    将 scene_record_content 放入 edges_var.edges_prompt_vars，供提示词占位符 {scene_record_content} 替换；
    current_message 为一句引导输出 JSON 的用户消息。

    Args:
        scene_record_content: 当前 md 的完整正文。
        file_id: 用于生成 session_id 的标识（如文件名或路径 hash）。

    Returns:
        FlowState 初始状态。
    """
    session_id = f"{SESSION_ID_PREFIX}{file_id}" if file_id else f"{SESSION_ID_PREFIX}single"
    return {
        "current_message": HumanMessage(content="请根据上述规则，对输入的「场景独立记录正文」进行提取，仅输出 JSON。"),
        "history_messages": [],
        "flow_msgs": [],
        "session_id": session_id,
        "token_id": TOKEN_ID_PLACEHOLDER,
        "trace_id": None,
        "prompt_vars": {},
        "edges_var": {
            "edges_prompt_vars": {
                "scene_record_content": scene_record_content or "",
            },
        },
    }


def extract_model_output_from_final_state(final_state: dict) -> str:
    """
    从 ainvoke 返回的最终 state 中取出模型回复文本。

    Agent 节点将输出写入 flow_msgs 的最后一条 AIMessage.content。

    Args:
        final_state: graph.ainvoke 返回的 state。

    Returns:
        模型回复文本；若无则返回空字符串。
    """
    flow_msgs = final_state.get("flow_msgs") or []
    if not flow_msgs:
        return ""
    last_msg = flow_msgs[-1]
    content = getattr(last_msg, "content", None)
    return (content or "").strip()


async def run_flow(graph: Any, scene_record_content: str, file_id: str = "") -> str:
    """
    执行单节点 flow，返回模型回复文本。

    Args:
        graph: FlowManager.get_flow 返回的编译图。
        scene_record_content: 当前 md 的完整正文。
        file_id: 用于 session_id 的标识。

    Returns:
        模型回复文本（即 JSON 或带 markdown 的文本）。
    """
    initial_state = build_initial_state(scene_record_content, file_id=file_id)
    config: dict = {"configurable": {"thread_id": initial_state["session_id"]}}
    final_state = await graph.ainvoke(initial_state, config)
    return extract_model_output_from_final_state(final_state)
