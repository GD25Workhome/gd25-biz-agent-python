"""
LSK 清洗器：4.1 lsk_副本.xlsx

列映射：新会话、新会话响应、ids、历史会话、历史会话响应、年龄、疾病、血压、症状、用药、用药情况、习惯、历史Action、ext
1 行 → 1 CanonicalItem
"""
import re
from typing import Any, Dict, List, Optional

import pandas as pd

from scripts.import_to_datasets.feishu_ceshi_case.parsers.base import (
    _is_empty_like,
    convert_to_int,
    convert_to_string,
    convert_to_text,
)
from scripts.import_to_datasets.feishu_ceshi_case.parsers.canonical import CanonicalItem
from scripts.import_to_datasets.feishu_ceshi_case.parsers.cleaners.base import BaseSheetCleaner


def strip_content_prefix(text: Optional[str]) -> str:
    """
    去掉 content= 或 content： 前缀。

    用于「新会话响应」等字段，将 "content=实际内容" 转为 "实际内容"。
    支持 content=、content： 两种形式。

    Returns:
        str: 去掉前缀后的内容，空输入返回 ""
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
    大小写不敏感。

    Returns:
        {"message_id": str|None, "patient_id": str|None, "doctor_id": str|None}
    """
    result: Dict[str, Optional[str]] = {
        "message_id": None,
        "patient_id": None,
        "doctor_id": None,
    }
    if pd.isna(value) or value is None:
        return result
    value_str = str(value).strip()
    if _is_empty_like(value_str):
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

    # 兼容：无 messageId 前缀时，若为单行纯 ID，作为 message_id
    if result["message_id"] is None and "\n" not in value_str and ":" not in value_str:
        result["message_id"] = value_str
    return result


def parse_lsk_history_session(text: Optional[str]) -> List[str]:
    """
    从「历史会话」列解析 human 消息内容列表。

    格式：第N轮提问-----------、messageId: xxx、实际提问内容，多轮重复。
    剔除：第N轮提问行、messageId 行，保留实际提问内容。

    Returns:
        List[str]: human 消息内容列表 [Q1, Q2, ...]
    """
    if not text or not str(text).strip():
        return []
    content = str(text).strip()
    # 去除末尾分隔符 ====== 等
    # content = re.sub(r"\s*[=]+$", "", content).strip()
    if not content:
        return []

    # 按 第N轮提问 分割
    blocks = re.split(r"第\d+轮提问[-=]*\s*", content)
    result: List[str] = []
    # messageId 行正则（整行匹配）
    msg_id_line = re.compile(r"^\s*message[_\s]?[iI]d\s*[:：]\s*\S+\s*$", re.MULTILINE)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # 剔除 messageId 行
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
    剔除：第N轮响应 行，提取 content= 或 content： 后的值。

    Returns:
        List[str]: ai 消息内容列表 [A1, A2, ...]
    """
    if not text or not str(text).strip():
        return []
    content = str(text).strip()
    # 去除末尾分隔符 >>> 等
    content = re.sub(r"\s*[>]+$", "", content).strip()
    if not content:
        return []

    # 按 第N轮响应 分割
    blocks = re.split(r"第\d+轮响应\s*", content)
    result: List[str] = []
    # 提取 content= 或 content： 后的值
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
            # 无 content= 时，整块作为 content（兼容）
            if block:
                result.append(block)
    return result


def merge_history_to_messages(
    humans: List[str],
    ais: List[str],
) -> List[Dict[str, str]]:
    """
    将 human 与 ai 列表交替合并为 history_messages。

    若轮数不一致，以较短者为准。

    Returns:
        [{"type":"human","content":...},{"type":"ai","content":...}, ...]
    """
    messages: List[Dict[str, str]] = []
    n = min(len(humans), len(ais))
    for i in range(n):
        messages.append({"type": "human", "content": humans[i]})
        messages.append({"type": "ai", "content": ais[i]})
    return messages


class LskCleaner(BaseSheetCleaner):
    """4.1 lsk_副本.xlsx 清洗器"""

    _CURRENT_COL = "新会话"
    _RESPONSE_COL = "新会话响应"
    _MSG_ID_COL = "ids"
    _HISTORY_SESSION_COL = "历史会话"
    _HISTORY_RESPONSE_COL = "历史会话响应"
    _CONTEXT_COL_MAP = {
        "age": "年龄",
        "disease": "疾病",
        "blood_pressure": "血压",
        "symptom": "症状",
        "medication": "用药",
        "medication_status": "用药情况",
        "habit": "习惯",
        "history_action": "历史Action",
    }

    def is_empty_row(self, row: pd.Series, df: pd.DataFrame) -> bool:
        if self._CURRENT_COL not in df.columns or self._RESPONSE_COL not in df.columns:
            return True
        current = convert_to_text(row.get(self._CURRENT_COL))
        response = convert_to_text(row.get(self._RESPONSE_COL))
        return current is None or response is None

    def _extract_context(self, row: pd.Series, df: pd.DataFrame) -> Dict[str, Any]:
        """提取 context 字段（年龄、疾病、血压、症状、用药、用药情况、习惯、历史Action）"""
        ctx: Dict[str, Any] = {}
        for key, col in self._CONTEXT_COL_MAP.items():
            if col not in df.columns:
                continue
            if key == "age":
                v = convert_to_int(row.get(col))
            elif key in ("disease", "blood_pressure", "medication", "medication_status", "habit", "history_action"):
                v = convert_to_string(row.get(col), 500 if key != "blood_pressure" else 200)
            else:
                v = convert_to_text(row.get(col))
            if v is not None:
                ctx[key] = v
        return ctx

    def _parse_history_messages(
        self,
        history_session: Optional[str],
        history_response: Optional[str],
    ) -> List[Dict[str, str]]:
        """
        将历史会话、历史会话响应解析为 history_messages。

        LSK 格式：第N轮提问、第N轮响应，交替合并为 [human, ai, human, ai, ...]。
        """
        humans = parse_lsk_history_session(history_session)
        ais = parse_lsk_history_response(history_response)
        return merge_history_to_messages(humans, ais)

    def clean(self, row: pd.Series, df: pd.DataFrame) -> List[CanonicalItem]:
        current = convert_to_text(row.get(self._CURRENT_COL)) or ""
        response_raw = convert_to_text(row.get(self._RESPONSE_COL)) or ""
        response = strip_content_prefix(response_raw)

        ids_data = (
            extract_lsk_ids(row.get(self._MSG_ID_COL))
            if self._MSG_ID_COL in df.columns
            else {"message_id": None, "patient_id": None, "doctor_id": None}
        )

        context = self._extract_context(row, df)
        ext = convert_to_text(row.get("ext")) if "ext" in df.columns else None

        history_session = (
            convert_to_text(row.get(self._HISTORY_SESSION_COL))
            if self._HISTORY_SESSION_COL in df.columns
            else None
        )
        history_response = (
            convert_to_text(row.get(self._HISTORY_RESPONSE_COL))
            if self._HISTORY_RESPONSE_COL in df.columns
            else None
        )
        history_messages = self._parse_history_messages(history_session, history_response)

        return [
            CanonicalItem(
                current_msg=current,
                history_messages=history_messages,
                response_message=response,
                message_id=ids_data["message_id"],
                patient_id=ids_data["patient_id"],
                doctor_id=ids_data["doctor_id"],
                context=context,
                ext=ext,
            )
        ]
