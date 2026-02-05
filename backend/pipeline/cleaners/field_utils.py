"""
字段转换工具

供各清洗器复用的空值判断、类型转换、解析函数。
设计文档：cursor_docs/020402-数据导入流程技术设计.md
"""
import re
from typing import Any, Dict, List, Optional

import pandas as pd

# 视为空的字符串（strip 后）或仅由连字符组成的字符串
_EMPTY_VALUES = frozenset({"", "无", "-", "—", "–"})


def is_empty_like(s: str) -> bool:
    """
    判断字符串是否视为空（含 "-"、"--"、全角/en-dash 等）。
    """
    if not s:
        return True
    t = str(s).strip()
    if not t:
        return True
    if t in _EMPTY_VALUES:
        return True
    cleaned = t.replace("-", "").replace("—", "").replace("–", "").strip()
    return cleaned == ""


def convert_to_int(value: Any) -> Optional[int]:
    """将值转换为整数，空或"无"或"-"返回 None"""
    if pd.isna(value) or value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            value = value.strip()
            if is_empty_like(value):
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
    if is_empty_like(result):
        return None
    if max_length and len(result) > max_length:
        result = result[:max_length]
    return result


def convert_to_text(value: Any) -> Optional[str]:
    """将值转换为文本，空或"无"或"-"返回 None"""
    if pd.isna(value) or value is None:
        return None
    result = str(value).strip()
    if is_empty_like(result):
        return None
    return result


def strip_content_prefix(text: Optional[str]) -> str:
    """
    去掉 content= 或 content： 前缀。
    用于「新会话响应」等字段。
    """
    if not text:
        return ""
    s = str(text).strip()
    if not s:
        return ""
    m = re.match(r"^content\s*[=：]\s*", s, re.IGNORECASE)
    if m:
        return s[m.end() :].strip()
    return s


def extract_lsk_ids(value: Any) -> Dict[str, Optional[str]]:
    """
    从 ids 列提取 messageId、patientid、doctorid。
    支持 messageId: xxx、patientid: xxx、doctorid: xxx 格式（换行分隔）。
    """
    result: Dict[str, Optional[str]] = {
        "message_id": None,
        "patient_id": None,
        "doctor_id": None,
    }
    if pd.isna(value) or value is None:
        return result
    value_str = str(value).strip()
    if is_empty_like(value_str):
        return result

    patterns = [
        (r"message[_\s]?[iI]d\s*[:：]\s*([^\s\n\r;,\"]+)", "message_id"),
        (r"patient[_\s]?[iI]d\s*[:：]\s*([^\s\n\r;,\"]+)", "patient_id"),
        (r"doctor[_\s]?[iI]d\s*[:：]\s*([^\s\n\r;,\"]+)", "doctor_id"),
    ]
    for pattern, key in patterns:
        match = re.search(pattern, value_str, re.IGNORECASE)
        if match:
            result[key] = match.group(1).strip()

    if result["message_id"] is None and "\n" not in value_str and ":" not in value_str:
        result["message_id"] = value_str
    return result


def parse_lsk_history_session(text: Optional[str]) -> List[str]:
    """
    从「历史会话」列解析 human 消息内容列表。
    格式：第N轮提问-----------、messageId: xxx、实际提问内容，多轮重复。
    """
    if not text or not str(text).strip():
        return []
    content = str(text).strip()
    if not content:
        return []

    blocks = re.split(r"第\d+轮提问[-=]*\s*", content)
    result: List[str] = []
    msg_id_line = re.compile(r"^\s*message[_\s]?[iI]d\s*[:：]\s*\S+\s*$", re.MULTILINE)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        kept = []
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            if msg_id_line.match(line_stripped):
                continue
            kept.append(line_stripped)
        if kept:
            result.append("\n".join(kept))
    return result


def parse_lsk_history_response(text: Optional[str]) -> List[str]:
    """
    从「历史会话响应」列解析 ai 消息内容列表。
    格式：第N轮响应、content=...，多轮重复。
    """
    if not text or not str(text).strip():
        return []
    content = str(text).strip()
    content = re.sub(r"\s*[>]+$", "", content).strip()
    if not content:
        return []

    blocks = re.split(r"第\d+轮响应\s*", content)
    result: List[str] = []
    content_pattern = re.compile(r"content\s*[=：]\s*([\s\S]*)", re.IGNORECASE)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        match = content_pattern.search(block)
        if match:
            val = match.group(1).strip()
            if val:
                result.append(val)
        else:
            if block:
                result.append(block)
    return result


def merge_history_to_messages(
    humans: List[str],
    ais: List[str],
) -> List[Dict[str, str]]:
    """
    将 human 与 ai 列表交替合并为 history_messages。
    Returns: [{"type":"human","content":...},{"type":"ai","content":...}, ...]
    """
    messages: List[Dict[str, str]] = []
    n = min(len(humans), len(ais))
    for i in range(n):
        messages.append({"type": "human", "content": humans[i]})
        messages.append({"type": "ai", "content": ais[i]})
    return messages


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
    if is_empty_like(value_str):
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
    pattern = r"(?:^|\n)\s*[Aa][：:]\s*([\s\S]+?)(?=\n\s*[Aa][：:]|\Z)"
    matches = re.findall(pattern, content)
    return [m.strip() for m in matches if m.strip()]
