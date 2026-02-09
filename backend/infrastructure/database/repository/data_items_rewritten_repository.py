"""
改写后数据项仓储实现
支持按场景描述、改写后问题/回答/规则、来源 ID、场景类型等筛选，分页、total。
设计文档：doc/总体设计规划/数据归档-schema/Step2-数据初步筛选.md
"""
from typing import List, Optional, Tuple
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.data_items_rewritten import DataItemsRewrittenRecord


def _add_ilike_condition(conditions: list, field, value: Optional[str]) -> None:
    """若 value 非空，添加 ilike 模糊匹配条件"""
    if value and value.strip():
        conditions.append(field.ilike(f"%{value.strip()}%"))


class DataItemsRewrittenRepository(BaseRepository[DataItemsRewrittenRecord]):
    """改写后数据项仓储类"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DataItemsRewrittenRecord)

    async def get_list_with_total(
        self,
        scenario_description: Optional[str] = None,
        rewritten_question: Optional[str] = None,
        rewritten_answer: Optional[str] = None,
        rewritten_rule: Optional[str] = None,
        source_dataset_id: Optional[str] = None,
        source_item_id: Optional[str] = None,
        scenario_type: Optional[str] = None,
        sub_scenario_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[DataItemsRewrittenRecord], int]:
        """
        分页查询，支持场景描述、改写后问题/回答/规则、来源 ID、场景类型、子场景类型筛选。
        文本字段使用 ilike 模糊匹配。
        """
        conditions = []
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.scenario_description,
            scenario_description,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.rewritten_question,
            rewritten_question,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.rewritten_answer,
            rewritten_answer,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.rewritten_rule,
            rewritten_rule,
        )
        # 来源 dataSetsId、dataItemsId 使用精确匹配
        if source_dataset_id and source_dataset_id.strip():
            conditions.append(
                DataItemsRewrittenRecord.source_dataset_id == source_dataset_id.strip()
            )
        if source_item_id and source_item_id.strip():
            conditions.append(
                DataItemsRewrittenRecord.source_item_id == source_item_id.strip()
            )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.scenario_type,
            scenario_type,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.sub_scenario_type,
            sub_scenario_type,
        )

        base_query = select(DataItemsRewrittenRecord)
        count_query = select(func.count()).select_from(DataItemsRewrittenRecord)
        if conditions:
            base_query = base_query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        list_query = (
            base_query.order_by(DataItemsRewrittenRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(list_query)
        items = list(result.scalars().all())
        return items, total

    async def get_by_source_item_id(
        self,
        source_item_id: str,
    ) -> Optional[DataItemsRewrittenRecord]:
        """按 source_item_id 查询单条（一个原始项可能对应一条改写结果）。"""
        stmt = select(DataItemsRewrittenRecord).where(
            DataItemsRewrittenRecord.source_item_id == source_item_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
