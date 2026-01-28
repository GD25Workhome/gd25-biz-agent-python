"""
将单条 case 转为 KnowledgeBaseRecord 并插入；含 source_meta、raw_material_full_text。
"""
import json
import logging
from typing import Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.models.knowledge_base import KnowledgeBaseRecord
from backend.infrastructure.database.repository.knowledge_base_repository import (
    KnowledgeBaseRepository,
)

logger = logging.getLogger(__name__)


def _case_to_record_fields(
    case: Dict[str, Any],
    source_file_rel: str,
    raw_material_full_text: str,
) -> Dict[str, Any]:
    """
    将单条 case 与来源信息转为 KnowledgeBaseRecord 的字段字典。

    optimization_question 若为 list 则 json.dumps 存为字符串；input_tags/response_tags 保持 list（JSONB）。
    """
    opt_q = case.get("optimization_question")
    if isinstance(opt_q, list):
        optimization_question = json.dumps(opt_q, ensure_ascii=False)
    else:
        optimization_question = str(opt_q) if opt_q is not None else None

    return {
        "scene_summary": (case.get("scene_summary") or "").strip() or None,
        "optimization_question": optimization_question,
        "reply_example_or_rule": (case.get("reply_example_or_rule") or "").strip() or None,
        "scene_category": (case.get("scene_category") or "").strip() or None,
        "input_tags": case.get("input_tags") if isinstance(case.get("input_tags"), list) else None,
        "response_tags": case.get("response_tags") if isinstance(case.get("response_tags"), list) else None,
        "raw_material_full_text": raw_material_full_text or None,
        "source_meta": {"source_file": source_file_rel} if source_file_rel else None,
    }


async def save_cases(
    session: AsyncSession,
    cases: List[Dict[str, Any]],
    source_file_rel: str,
    raw_material_full_text: str,
) -> int:
    """
    将 cases 列表逐条写入 knowledge_base 表。

    Args:
        session: 异步数据库会话。
        cases: 解析出的 cases 列表。
        source_file_rel: 相对项目根的来源文件路径。
        raw_material_full_text: 当前 md 的完整原文。

    Returns:
        成功写入条数。
    """
    if not cases:
        return 0
    repo = KnowledgeBaseRepository(session)
    count = 0
    for case in cases:
        fields = _case_to_record_fields(case, source_file_rel, raw_material_full_text)
        try:
            await repo.create(**fields)
            count += 1
        except Exception as e:
            logger.warning("写入单条 case 失败: %s, fields_keys=%s", e, list(fields.keys()), exc_info=True)
    return count
