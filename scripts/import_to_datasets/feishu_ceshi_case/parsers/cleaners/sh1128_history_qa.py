"""
Sh1128 历史会话 Q/A 清洗器：患者无数据+历史会话+历史Action Sheet

继承 Sh1128Cleaner，重写 _parse_history_messages()：历史会话字段为 Q/A 格式，
解析为多轮 [human, ai, human, ai, ...]。
"""
import re
from typing import List, Optional

import pandas as pd

from scripts.import_to_datasets.feishu_ceshi_case.parsers.cleaners.sh1128 import Sh1128Cleaner


def _parse_history_qa_to_messages(text: Optional[str]) -> List[dict]:
    """
    将「历史会话」Q/A 格式解析为 BaseMessage 数组。

    格式：Q：xxx / Q: xxx、A：xxx / A: xxx 交替出现。
    支持末尾分隔符如 ----。

    Returns:
        [{"type":"human","content":"Q1"}, {"type":"ai","content":"A1"}, ...]
    """
    if not text or not str(text).strip():
        return []
    content = str(text).strip()
    # 去除末尾 ----、--- 等分隔符
    content = re.sub(r"\s*[-—–]+\s*$", "", content).strip()
    if not content:
        return []

    # 按 Q：/Q:、A：/A: 切分，保留顺序。使用 findall 匹配 (标记, 内容) 对
    # 匹配 [QqAa][：:] 开头的块
    pattern = r"([QqAa])[：:]\s*([\s\S]+?)(?=[QqAa][：:]|\Z)"
    matches = re.findall(pattern, content)
    if not matches:
        # 无法解析，整段作为 human
        return [{"type": "human", "content": content}]

    messages: List[dict] = []
    for prefix, block in matches:
        block = block.strip()
        if not block:
            continue
        if prefix.lower() == "q":
            messages.append({"type": "human", "content": block})
        else:
            messages.append({"type": "ai", "content": block})
    return messages


class Sh1128HistoryQACleaner(Sh1128Cleaner):
    """患者无数据+历史会话+历史Action：历史会话 Q/A 解析"""

    def _parse_history_messages(
        self,
        history_session: Optional[str],
        history_response: Optional[str],
    ) -> List[dict]:
        # 历史会话为 Q/A 格式时，解析为多轮
        if history_session:
            parsed = _parse_history_qa_to_messages(history_session)
            if parsed:
                return parsed
        # 无法解析时，退化为父类单条 human + ai
        return super()._parse_history_messages(history_session, history_response)
