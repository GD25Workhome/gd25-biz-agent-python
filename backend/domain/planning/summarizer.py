"""
Plan-and-Execute 工具结果摘要
"""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def summarize_tool_result(raw: Any, max_chars: int = 2000) -> str:
    """
    将工具或 Agent 原始返回压缩为 Replanner 可消费的摘要。

    Args:
        raw: 原始返回值（str、dict、list 等）
        max_chars: 摘要最大字符数

    Returns:
        str: 压缩后的摘要文本
    """
    if raw is None:
        return ""

    if isinstance(raw, str):
        text = raw.strip()
    elif isinstance(raw, (dict, list)):
        try:
            text = json.dumps(raw, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(raw)
    else:
        text = str(raw)

    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    logger.debug(
        "工具结果已截断摘要: 原始长度=%d, 截断后=%d",
        len(text),
        len(truncated),
    )
    return truncated + "\n...[结果已截断]"
