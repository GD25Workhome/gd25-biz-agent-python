"""
解析器基类与字段处理工具

包含：
- DataSetItemData：DataSet Item 基础数据结构
- 字段转换函数（供 cleaners 复用）
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd


# ---------- DataSet Item 数据结构 ----------


@dataclass
class DataSetItemData:
    """DataSet Item 基础数据，对应 Input/Output Schema"""

    # Input 部分
    input: Dict[str, Any] = field(default_factory=dict)
    # Output (expected_output) 部分
    expected_output: Dict[str, Any] = field(default_factory=dict)
    # Item 级 metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------- 空值判断（含 "-" 兼容） ----------

# 视为空的字符串（strip 后）或仅由连字符组成的字符串
_EMPTY_VALUES = frozenset({"", "无", "-", "—", "–"})


def _is_empty_like(s: str) -> bool:
    """
    判断字符串是否视为空（含 "-"、"--"、全角/en-dash 等）。

    用于 convert_to_text、convert_to_string 等，统一空值判断。
    """
    if not s:
        return True
    t = s.strip()
    if not t:
        return True
    if t in _EMPTY_VALUES:
        return True
    # 仅由 -、—、–、空格 组成
    cleaned = t.replace("-", "").replace("—", "").replace("–", "").strip()
    return cleaned == ""


# ---------- 字段转换函数（责任链中的处理器可复用） ----------


def convert_to_int(value: Any) -> Optional[int]:
    """将值转换为整数，空或"无"或"-"返回 None"""
    if pd.isna(value) or value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            value = value.strip()
            if _is_empty_like(value):
                return None
            return int(float(value))
        if isinstance(value, float):
            return int(value)
        return int(value)
    except (ValueError, TypeError):
        return None


def convert_to_string(value: Any, max_length: Optional[int] = None) -> Optional[str]:
    """将值转换为字符串，空或"无"或"-"返回 None"""
    if pd.isna(value) or value is None:
        return None
    result = str(value).strip()
    if _is_empty_like(result):
        return None
    if max_length and len(result) > max_length:
        result = result[:max_length]
    return result


def convert_to_text(value: Any) -> Optional[str]:
    """将值转换为文本，空或"无"或"-"返回 None"""
    if pd.isna(value) or value is None:
        return None
    result = str(value).strip()
    if _is_empty_like(result):
        return None
    return result


def extract_message_id(value: Any) -> Optional[str]:
    """
    从 ids 或 message_id 列提取 message_id。
    支持纯 UUID 或 messageId: xxx 格式。
    """
    ids = extract_message_ids(value)
    return ids[0] if ids else None


def extract_message_ids(value: Any) -> List[str]:
    """
    从 message_id 列提取多个 message_id，支持多行/多值。

    支持：
    - 换行分隔（\\n、\\r\\n）
    - 分号、逗号分隔
    - messageId: xxx、message_id: xxx 格式
    - 纯 UUID

    Returns:
        List[str]: message_id 列表，空则返回 []
    """
    if pd.isna(value) or value is None:
        return []
    value_str = str(value).strip()
    if _is_empty_like(value_str):
        return []
    # 先尝试按 messageId: xxx 格式批量提取
    patterns = [
        r"messageId\s*[:：]\s*([^\s\n\r;,\"]+)",
        r"message_id\s*[:：]\s*([^\s\n\r;,\"]+)",
        r"messageId\s*=\s*([^\s\n\r;,\"]+)",
        r"message_id\s*=\s*([^\s\n\r;,\"]+)",
    ]
    found: List[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, value_str, re.IGNORECASE):
            msg_id = match.group(1).strip()
            if msg_id and msg_id not in found:
                found.append(msg_id)
    if found:
        return found
    # 无 messageId 前缀时，按换行、分号、逗号分割
    parts = re.split(r"[\n\r;,\t]+", value_str)
    return [p.strip() for p in parts if p.strip()]


def parse_qa_blocks(text: Optional[str]) -> List[str]:
    """
    从「会话输入」字段提取 Q 块列表。

    按 Q：、Q: 分割，取每个 Q 后的内容直到下一个 Q 或 A 标记。
    支持中英文冒号。

    Returns:
        List[str]: 用户提问列表 [Q1, Q2, ...]
    """
    if not text or not str(text).strip():
        return []
    content = str(text).strip()
    # 匹配 Q： 或 Q: 后的内容，直到下一个 Q/A 或结尾
    pattern = r"[Qq][：:]\s*([\s\S]+?)(?=[QqAa][：:]|\Z)"
    matches = re.findall(pattern, content)
    return [m.strip() for m in matches if m.strip()]


def parse_response_blocks(text: Optional[str]) -> List[str]:
    """
    从「供应商响应」字段提取 A 块列表。

    按行首的 A: 或 A： 分割，每个块可包含 [未知类型(tool_xxx): {...}] 等 tool 标记。
    支持中英文冒号。

    Returns:
        List[str]: 供应商响应列表 [A1, A2, ...]
    """
    if not text or not str(text).strip():
        return []
    content = str(text).strip()
    # 匹配行首或字符串开头的 A: 或 A：，提取内容直到下一个 A 块或结尾
    pattern = r"(?:^|\n)\s*[Aa][：:]\s*([\s\S]+?)(?=\n\s*[Aa][：:]|\Z)"
    matches = re.findall(pattern, content)
    return [m.strip() for m in matches if m.strip()]


