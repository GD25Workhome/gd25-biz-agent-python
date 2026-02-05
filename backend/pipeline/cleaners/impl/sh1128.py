"""
Sh1128 通用清洗器：sh-1128_副本.xlsx 父类

列映射：会话输入、供应商响应()、历史会话、历史会话响应、message_id、patient_id
1 行 → 1 CanonicalItem，history_session/history_response 作为单条 human/ai。
子类可重写 clean() 或 _parse_history_messages() 实现定制逻辑。
设计文档：cursor_docs/020402-数据导入流程技术设计.md
"""
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.pipeline.cleaners.base import BaseSheetCleaner
from backend.pipeline.cleaners.canonical import CanonicalItem
from backend.pipeline.cleaners.field_utils import (
    convert_to_int,
    convert_to_string,
    convert_to_text,
    extract_message_id,
)


class Sh1128Cleaner(BaseSheetCleaner):
    """sh-1128_副本.xlsx 通用清洗器（父类）"""

    _CURRENT_COL = "会话输入"
    _RESPONSE_COL = "供应商响应()"
    _HISTORY_SESSION_COL = "历史会话"
    _HISTORY_RESPONSE_COL = "历史会话响应"
    _MSG_ID_COL = "message_id"
    _PATIENT_ID_COL = "patient_id"
    _CONTEXT_KEYS = ["age", "disease", "blood_pressure", "symptom", "medication", "medication_status", "habit"]
    _CONTEXT_COL_MAP = {
        "age": "年龄",
        "disease": "疾病",
        "blood_pressure": "血压",
        "symptom": "症状",
        "medication": "用药",
        "medication_status": "用药情况",
        "habit": "习惯",
    }

    def is_empty_row(self, row: pd.Series, df: pd.DataFrame) -> bool:
        if self._CURRENT_COL not in df.columns or self._RESPONSE_COL not in df.columns:
            return True
        current = convert_to_text(row.get(self._CURRENT_COL))
        response = convert_to_text(row.get(self._RESPONSE_COL))
        return current is None or response is None

    def _parse_history_messages(
        self,
        history_session: Optional[str],
        history_response: Optional[str],
    ) -> List[Dict[str, str]]:
        """
        将历史会话、历史会话响应转为 history_messages。

        默认：单条 human + 单条 ai。
        子类可重写以支持 Q/A 格式解析（如 Sh1128HistoryQACleaner）。
        """
        messages: List[Dict[str, str]] = []
        if history_session:
            messages.append({"type": "human", "content": history_session})
        if history_response:
            messages.append({"type": "ai", "content": history_response})
        return messages

    def _extract_context(self, row: pd.Series, df: pd.DataFrame) -> Dict[str, Any]:
        """提取 context 字段"""
        ctx: Dict[str, Any] = {}
        for key, col in self._CONTEXT_COL_MAP.items():
            if col not in df.columns:
                continue
            if key == "age":
                v = convert_to_int(row.get(col))
            elif key in ("disease", "blood_pressure", "medication", "medication_status", "habit"):
                v = convert_to_string(row.get(col), 500 if key != "blood_pressure" else 200)
            else:
                v = convert_to_text(row.get(col))
            if v is not None:
                ctx[key] = v
        return ctx

    def clean(self, row: pd.Series, df: pd.DataFrame) -> List[CanonicalItem]:
        current = convert_to_text(row.get(self._CURRENT_COL)) or ""
        response = convert_to_text(row.get(self._RESPONSE_COL)) or ""
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
        msg_id = extract_message_id(row.get(self._MSG_ID_COL)) if self._MSG_ID_COL in df.columns else None
        patient_id = convert_to_string(row.get(self._PATIENT_ID_COL)) if self._PATIENT_ID_COL in df.columns else None
        context = self._extract_context(row, df)
        ext = convert_to_text(row.get("ext")) if "ext" in df.columns else None
        return [
            CanonicalItem(
                current_msg=current,
                history_messages=history_messages,
                response_message=response,
                message_id=msg_id,
                patient_id=patient_id,
                context=context,
                ext=ext,
            )
        ]
