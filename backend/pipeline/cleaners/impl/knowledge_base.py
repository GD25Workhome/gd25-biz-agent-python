"""
KnowledgeBase 清洗器：gd2502_knowledge_base 表

将知识库表行清洗为 CanonicalItem，1 行 → 1 条。
设计文档：cursor_docs/020507-gd2502_knowledge_base导入流程技术设计.md
"""
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.pipeline.cleaners.base import BaseSheetCleaner
from backend.pipeline.cleaners.canonical import CanonicalItem

logger = logging.getLogger(__name__)

_REPLY_RULE_PREFIX = "回复规则："


def _compute_unique_key(
    scene_summary: Optional[str],
    optimization_question: Optional[str],
    reply_example_or_rule: Optional[str],
) -> str:
    """使用 MD5 将三字段拼接后计算 unique_key"""
    parts = [
        (scene_summary or "").strip(),
        (optimization_question or "").strip(),
        (reply_example_or_rule or "").strip(),
    ]
    content = "\n".join(parts)
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _parse_optimization_question(value: Any) -> str:
    """
    解析 optimization_question，可能为 JSON 数组字符串。
    取第一个元素作为 current_msg；解析失败则原样使用。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("["):
        try:
            arr = json.loads(text)
            if isinstance(arr, list) and arr:
                first = arr[0]
                return str(first).strip() if first is not None else ""
        except (json.JSONDecodeError, TypeError):
            pass
    return text


class KnowledgeBaseCleaner(BaseSheetCleaner):
    """gd2502_knowledge_base 表清洗器"""

    def is_empty_row(self, row: pd.Series, df: pd.DataFrame) -> bool:
        opt_str = self._to_str(row.get("optimization_question"))
        reply_str = self._to_str(row.get("reply_example_or_rule"))
        return not opt_str and not reply_str

    def clean(self, row: pd.Series, df: pd.DataFrame) -> List[CanonicalItem]:
        scene_summary = self._to_str(row.get("scene_summary"))
        optimization_question_raw = row.get("optimization_question")
        optimization_question = self._to_str(optimization_question_raw)
        reply_example_or_rule = self._to_str(row.get("reply_example_or_rule"))
        scene_category = self._to_str(row.get("scene_category"))
        input_tags = row.get("input_tags")
        response_tags = row.get("response_tags")
        raw_material_full_text = self._to_str(row.get("raw_material_full_text"))

        current_msg = _parse_optimization_question(optimization_question_raw)

        if reply_example_or_rule.startswith(_REPLY_RULE_PREFIX):
            response_message = ""
            response_rule = reply_example_or_rule[len(_REPLY_RULE_PREFIX) :].strip()
        else:
            response_message = reply_example_or_rule
            response_rule = None

        original_extract: Dict[str, Any] = {
            "scene_summary": scene_summary,
            "scene_category": scene_category,
            "input_tags": input_tags if isinstance(input_tags, (list, type(None))) else None,
            "response_tags": response_tags if isinstance(response_tags, (list, type(None))) else None,
            "raw_material_full_text": raw_material_full_text,
        }

        record_id = row.get("id")
        source_meta = self._normalize_source_meta(row.get("source_meta"))
        if record_id is None or (isinstance(record_id, float) and pd.isna(record_id)):
            logger.warning("KnowledgeBase 行缺少 id 字段")
        step1_metadata: Dict[str, Any] = {
            "id": str(record_id) if record_id is not None else None,
            "source_meta": source_meta,
        }

        unique_key = _compute_unique_key(
            scene_summary,
            optimization_question,
            reply_example_or_rule,
        )

        return [
            CanonicalItem(
                current_msg=current_msg,
                history_messages=[],
                response_message=response_message,
                response_rule=response_rule,
                context={"original_extract": original_extract},
                step1_metadata=step1_metadata,
                unique_key=unique_key,
            )
        ]

    def _normalize_source_meta(self, val: Any) -> Optional[Dict[str, Any]]:
        """将 source_meta 规范化为 dict 或 None"""
        if val is None:
            return None
        if isinstance(val, dict):
            return val
        if isinstance(val, str) and val.strip().startswith("{"):
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return None
        return None

    def _to_str(self, val: Any) -> str:
        """将值转为字符串，None/NaN 返回空字符串"""
        if val is None:
            return ""
        if isinstance(val, float) and pd.isna(val):
            return ""
        return str(val).strip()
