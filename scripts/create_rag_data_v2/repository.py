"""
知识库写入封装模块（create_rag_data_v2 专用）。

职责：
- 将领域数据对象 KnowledgeBaseRecordData 写入数据库；
- 屏蔽 AsyncSession 与 KnowledgeBaseRepository 的具体使用细节。
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.models.knowledge_base import KnowledgeBaseRecord
from backend.infrastructure.database.repository.knowledge_base_repository import (
    KnowledgeBaseRepository,
)

from .parser import KnowledgeBaseRecordData


class KnowledgeBaseWriter:
    """
    知识库写入封装类。

    使用方式：
        async with session_factory() as session:
            writer = KnowledgeBaseWriter(session)
            await writer.insert_records(records)
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        初始化写入器。

        Args:
            session: AsyncSession 实例。
        """

        self._session = session
        self._repo = KnowledgeBaseRepository(session)

    async def insert_records(
        self,
        records: Iterable[KnowledgeBaseRecordData],
    ) -> int:
        """
        批量插入知识库记录。

        Args:
            records: 待写入的领域数据对象列表。

        Returns:
            int: 实际成功插入的记录数量。
        """

        count = 0
        for data in records:
            await self._repo.create(
                scene_summary=data.scene_summary,
                optimization_question=data.optimization_question,
                reply_example_or_rule=data.reply_example_or_rule,
                scene_category=data.scene_category,
                input_tags=data.input_tags or None,
                response_tags=data.response_tags or None,
                raw_material_full_text=data.raw_material_full_text,
                raw_material_scene_summary=None,
                raw_material_question=None,
                raw_material_answer=None,
                raw_material_other=None,
                source_meta=data.source_meta,
                technical_tag_classification=None,
                business_tag_classification=None,
            )
            count += 1

        # 由调用方负责提交事务（commit），这里仅返回计数
        return count


__all__ = [
    "KnowledgeBaseWriter",
    "KnowledgeBaseRecord",
]

