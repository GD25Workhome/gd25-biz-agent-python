"""
AutoGen TaskResult → FlowState 结果桥
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.messages import AIMessage

from backend.domain.flows.models.autogen_config import AutogenTeamNodeConfig
from backend.domain.state import FlowState, TeamResult, TeamTranscriptItem

logger = logging.getLogger(__name__)


def _message_content(message: Any) -> str:
    """提取 AutoGen 消息文本内容。"""
    content = getattr(message, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def _message_source(message: Any) -> str:
    """提取消息 source。"""
    return str(getattr(message, "source", "") or "")


def _message_type(message: Any) -> str:
    """提取消息类型名。"""
    type_attr = getattr(message, "type", None)
    if type_attr:
        return str(type_attr)
    return type(message).__name__


def _is_pure_approve(content: str, text_mention: str) -> bool:
    """
        判断消息是否为「纯批准」发言（正文候选时应跳过）。

        Args:
            content: 消息正文
            text_mention: 终止关键字

        Returns:
            是否视为纯批准
    """
    stripped = content.strip()
    if not stripped:
        return False
    if stripped == text_mention:
        return True
    # 短句且整段即为 mention（忽略首尾标点/空格）
    if text_mention in stripped and len(stripped) <= len(text_mention) + 8:
        return True
    return False


def extract_final_content_and_approved(
    messages: Sequence[Any],
    text_mention: str,
    content_max_chars: int,
) -> tuple[str, bool]:
    """
        按设计 §6.3 从后往前选取 final_content，并判定 approved。

        Args:
            messages: TaskResult.messages
            text_mention: 终止关键字
            content_max_chars: 正文截断上限

        Returns:
            (final_content, approved)
    """
    approved = False
    final_content = ""

    for message in reversed(list(messages)):
        source = _message_source(message)
        content = _message_content(message)
        if source == "user":
            continue
        if text_mention and text_mention in content:
            approved = True
            if _is_pure_approve(content, text_mention):
                continue
        if not final_content and content.strip() and not _is_pure_approve(content, text_mention):
            final_content = content.strip()

    if len(final_content) > content_max_chars:
        final_content = final_content[:content_max_chars]

    return final_content, approved


def _detect_hit_max_messages(stop_reason: Optional[str], message_count: int, max_messages: int) -> bool:
    """根据 stop_reason / 条数启发式判断是否触达 MaxMessageTermination。"""
    if stop_reason:
        lower = stop_reason.lower()
        if "maximum number of messages" in lower or "maxmessagetermination" in lower:
            return True
        if "maximum" in lower and "message" in lower:
            return True
    return message_count >= max_messages and (
        not stop_reason or text_mention_not_in_reason(stop_reason)
    )


def text_mention_not_in_reason(stop_reason: str) -> bool:
    """stop_reason 中未体现 text mention 时返回 True。"""
    return "mentioned" not in stop_reason.lower() and "text" not in stop_reason.lower()


def build_transcript(
    messages: Sequence[Any],
    *,
    max_items: int,
    content_max_chars: int,
) -> List[TeamTranscriptItem]:
    """
        构建限长 transcript。

        Args:
            messages: Team 消息序列
            max_items: 最多保留条数（取末尾）
            content_max_chars: 单条截断

        Returns:
            TeamTranscriptItem 列表
    """
    items: List[TeamTranscriptItem] = []
    for message in list(messages)[-max_items:]:
        content = _message_content(message)
        if len(content) > content_max_chars:
            content = content[:content_max_chars]
        items.append(
            {
                "source": _message_source(message),
                "content": content,
                "type": _message_type(message),
            }
        )
    return items


def to_flow_patch(
    result: Any,
    config: AutogenTeamNodeConfig,
    state: FlowState,
) -> Dict[str, Any]:
    """
        将 AutoGen TaskResult 转为 FlowState 补丁。

        Args:
            result: TaskResult（或具备 messages/stop_reason 的对象）
            config: 节点配置
            state: 当前 FlowState（用于 persistence 合并）

        Returns:
            可合并进 LangGraph 状态的 dict 补丁
    """
    messages = list(getattr(result, "messages", []) or [])
    stop_reason = getattr(result, "stop_reason", None)
    text_mention = config.termination.text_mention
    max_messages = config.termination.max_messages

    # 1. 提取正文与批准标志
    final_content, approved = extract_final_content_and_approved(
        messages,
        text_mention=text_mention,
        content_max_chars=config.output.content_max_chars,
    )
    hit_max = _detect_hit_max_messages(stop_reason, len(messages), max_messages)

    team_result: TeamResult = {
        "team_mode": config.team_mode,
        "stop_reason": stop_reason,
        "message_count": len(messages),
        "final_content": final_content,
        "approved": approved,
        "error": None,
        "timed_out": False,
        "hit_max_messages": hit_max and not approved,
    }

    edges_var: Dict[str, Any] = {
        "team_finished": True,
        config.output.edges_var_key: approved,
        "team_stop_reason": stop_reason or ("approved" if approved else "completed"),
    }

    patch: Dict[str, Any] = {
        "team_result": team_result,
        "edges_var": edges_var,
    }

    # 2. 写入 flow_msgs
    if config.output.write_to_flow_msgs:
        patch["flow_msgs"] = [AIMessage(content=final_content or "")]

    # 3. 可选 transcript
    if config.output.persist_transcript:
        patch["team_transcript"] = build_transcript(
            messages,
            max_items=config.output.max_transcript_messages,
            content_max_chars=config.output.content_max_chars,
        )

    # 4. 同步 persistence_edges_var（浅拷贝，避免污染上游）
    persist_keys = config.persist_to_persistence_edges_var
    if persist_keys:
        persistence = (state.get("persistence_edges_var") or {}).copy()
        for key in persist_keys:
            if key in edges_var:
                persistence[key] = edges_var[key]
        patch["persistence_edges_var"] = persistence

    logger.info(
        "autogen result_bridge: approved=%s message_count=%s stop_reason=%s",
        approved,
        len(messages),
        stop_reason,
    )
    return patch


def failure_flow_patch(
    config: AutogenTeamNodeConfig,
    state: FlowState,
    *,
    user_message: str,
    stop_reason: str,
    error: Optional[str],
    timed_out: bool,
) -> Dict[str, Any]:
    """
        构造超时 / 异常路径的 FlowState 补丁。

        Args:
            config: 节点配置
            state: 当前状态
            user_message: 面向用户的文案
            stop_reason: 短码（timeout / error）
            error: 错误摘要
            timed_out: 是否超时

        Returns:
            FlowState 补丁
    """
    team_result: TeamResult = {
        "team_mode": config.team_mode,
        "stop_reason": stop_reason,
        "message_count": 0,
        "final_content": user_message,
        "approved": False,
        "error": error,
        "timed_out": timed_out,
        "hit_max_messages": False,
    }
    edges_var: Dict[str, Any] = {
        "team_finished": True,
        config.output.edges_var_key: False,
        "team_stop_reason": stop_reason,
    }
    patch: Dict[str, Any] = {
        "team_result": team_result,
        "edges_var": edges_var,
    }
    if config.output.write_to_flow_msgs:
        patch["flow_msgs"] = [AIMessage(content=user_message)]

    persist_keys = config.persist_to_persistence_edges_var
    if persist_keys:
        persistence = (state.get("persistence_edges_var") or {}).copy()
        for key in persist_keys:
            if key in edges_var:
                persistence[key] = edges_var[key]
        patch["persistence_edges_var"] = persistence

    return patch
