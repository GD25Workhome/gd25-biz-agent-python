"""
state_builder 模块

职责：
- 从 MarkdownSource 构造 prompt_vars；
- 组装完整的 FlowState，供 create_rag_agent 流程使用。

设计对齐 scripts.embedding_import.core.state_builder，但仅保留
当前场景需要的最小字段，尤其是 scene_record_content 占位符。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from langchain_core.messages import HumanMessage

from backend.domain.state import FlowState

from .file_loader import MarkdownSource


TOKEN_ID_PLACEHOLDER: str = "create_rag_data_v2"
"""token_id 占位符，用于 RuntimeContext 与链路观测。"""

SESSION_ID_PREFIX: str = "create_rag_"
"""session_id 前缀，后接文件索引或哈希。"""


@dataclass
class PromptVars:
    """
    提示词变量封装。

    当前包含字段：
        - scene_record_content: 场景独立记录的完整 Markdown 正文；
        - source_file:          当前 Markdown 源文件的相对路径（用于入库时写入 source_meta.source_file）。
    如后续需要，可以在此处扩展其它辅助变量。
    """

    scene_record_content: str
    source_file: str


def build_prompt_vars_from_source(source: MarkdownSource) -> Dict[str, Any]:
    """
    根据 MarkdownSource 构造 prompt_vars 字典。

    Args:
        source: MarkdownSource 实例。

    Returns:
        dict: 可直接放入 FlowState["prompt_vars"] 的字典。
    """

    return {
        "scene_record_content": source.raw_markdown,
        # 将来源文件的相对路径放入 prompt_vars.source_file，供 insert_rag_data_node 使用
        "source_file": source.source_path,
    }


def build_initial_state_from_source(
    source: MarkdownSource,
    session_id: str,
    trace_id: str,
) -> FlowState:
    """
    根据 MarkdownSource 组装完整 FlowState。

    与 scripts.embedding_import.core.state_builder 中的 build_initial_state_from_record
    设计保持一致风格，但字段仅保留当前流程所必需的部分。

    Args:
        source:     当前处理的 Markdown 源文件。
        session_id: 会话标识，用于 LangGraph / Langfuse。
        trace_id:   链路追踪 ID。

    Returns:
        FlowState: 初始流程状态。
    """

    prompt_vars = build_prompt_vars_from_source(source)

    # 当前流程不依赖历史对话，history_messages 传空列表
    current_message = HumanMessage(content=source.raw_markdown)

    return {
        "current_message": current_message,
        "history_messages": [],
        "flow_msgs": [],
        "session_id": session_id,
        "token_id": TOKEN_ID_PLACEHOLDER,
        "trace_id": trace_id,
        "prompt_vars": prompt_vars,
    }


__all__ = [
    "TOKEN_ID_PLACEHOLDER",
    "SESSION_ID_PREFIX",
    "PromptVars",
    "build_prompt_vars_from_source",
    "build_initial_state_from_source",
]

