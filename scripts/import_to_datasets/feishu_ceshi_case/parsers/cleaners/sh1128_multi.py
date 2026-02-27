"""
Sh1128 多轮清洗器：常见问题及单轮 Sheet

继承 Sh1128Cleaner，重写 clean()：1 行 → 多 CanonicalItem。
会话输入、供应商响应() 按 Q/A 拆分，逐轮产出。
"""
import re
from typing import List, Optional

import pandas as pd

from scripts.import_to_datasets.feishu_ceshi_case.parsers.base import (
    convert_to_string,
    convert_to_text,
    extract_message_ids,
    parse_qa_blocks,
    parse_response_blocks,
)
from scripts.import_to_datasets.feishu_ceshi_case.parsers.canonical import CanonicalItem
from scripts.import_to_datasets.feishu_ceshi_case.parsers.cleaners.sh1128 import Sh1128Cleaner


class Sh1128MultiCleaner(Sh1128Cleaner):
    """常见问题及单轮：1 行 → 多 Item，Q/A 拆分"""

    def clean(self, row: pd.Series, df: pd.DataFrame) -> List[CanonicalItem]:
        if self._CURRENT_COL not in df.columns or self._RESPONSE_COL not in df.columns:
            return []

        session_text = convert_to_text(row.get(self._CURRENT_COL)) or ""
        response_text = convert_to_text(row.get(self._RESPONSE_COL)) or ""
        q_blocks = parse_qa_blocks(session_text)
        a_blocks = parse_response_blocks(response_text)

        if not q_blocks or not a_blocks:
            # 无法解析为多轮时，退化为父类单条
            return super().clean(row, df)

        n = min(len(q_blocks), len(a_blocks))
        msg_ids = extract_message_ids(row.get(self._MSG_ID_COL)) if self._MSG_ID_COL in df.columns else []
        while len(msg_ids) < n:
            msg_ids.append(None)
        msg_ids = msg_ids[:n]

        context = self._extract_context(row, df)
        patient_id = convert_to_string(row.get(self._PATIENT_ID_COL)) if self._PATIENT_ID_COL in df.columns else None
        ext = convert_to_text(row.get("ext")) if "ext" in df.columns else None

        result: List[CanonicalItem] = []
        history_messages: List[dict] = []

        for i in range(n):
            q, a = q_blocks[i], a_blocks[i]
            msg_id = msg_ids[i] if i < len(msg_ids) else None
            result.append(
                CanonicalItem(
                    current_msg=q,
                    history_messages=list(history_messages),
                    response_message=a,
                    message_id=msg_id,
                    patient_id=patient_id,
                    context=context,
                    ext=ext,
                )
            )
            history_messages.append({"type": "human", "content": q})
            history_messages.append({"type": "ai", "content": a})

        return result
