"""
LSK 清洗器：4.1 lsk_副本.xlsx

列映射：新会话、新会话响应、ids、历史会话、历史会话响应、年龄、疾病、血压、症状、用药、用药情况、习惯、历史Action、ext
1 行 → 1 CanonicalItem
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
    extract_lsk_ids,
    merge_history_to_messages,
    parse_lsk_history_response,
    parse_lsk_history_session,
    strip_content_prefix,
)


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
        """将历史会话、历史会话响应解析为 history_messages"""
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
                unique_key=ids_data["message_id"],
            )
        ]
