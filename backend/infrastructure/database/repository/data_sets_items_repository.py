"""
数据项仓储实现
支持按 dataset_id、unique_key、source、status、keyword 筛选，分页、total。
设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
"""
from typing import List, Optional, Tuple
from sqlalchemy import delete, select, func, and_, or_, cast
from sqlalchemy.types import Text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.data_sets_items import DataSetsItemsRecord


class DataSetsItemsRepository(BaseRepository[DataSetsItemsRecord]):
    """数据项仓储类"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DataSetsItemsRecord)

    async def get_list_with_total(
        self,
        dataset_id: str,
        status: Optional[int] = None,
        unique_key: Optional[str] = None,
        source: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[DataSetsItemsRecord], int]:
        """
        按 dataset_id 分页查询，支持 status、unique_key（包含）、source（包含）、keyword（在 input/output/metadata 中搜索）。
        """
        conditions = [DataSetsItemsRecord.dataset_id == dataset_id]
        if status is not None:
            conditions.append(DataSetsItemsRecord.status == status)
        if unique_key and unique_key.strip():
            conditions.append(DataSetsItemsRecord.unique_key.ilike(f"%{unique_key.strip()}%"))
        if source and source.strip():
            conditions.append(DataSetsItemsRecord.source.ilike(f"%{source.strip()}%"))
        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    cast(DataSetsItemsRecord.input, Text).ilike(kw),
                    cast(DataSetsItemsRecord.output, Text).ilike(kw),
                    cast(DataSetsItemsRecord.metadata_, Text).ilike(kw),
                )
            )

        base_query = select(DataSetsItemsRecord)
        count_query = select(func.count()).select_from(DataSetsItemsRecord)
        if conditions:
            base_query = base_query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        list_query = (
            base_query.order_by(DataSetsItemsRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(list_query)
        items = list(result.scalars().all())
        return items, total

    async def get_by_unique_key(
        self,
        dataset_id: str,
        unique_key: str,
    ) -> Optional[DataSetsItemsRecord]:
        """按 dataset_id + unique_key 查询单条。"""
        stmt = select(DataSetsItemsRecord).where(
            and_(
                DataSetsItemsRecord.dataset_id == dataset_id,
                DataSetsItemsRecord.unique_key == unique_key,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_all_by_dataset_id(self, dataset_id: str) -> int:
        """
        删除指定 dataset 下所有数据项。

        Args:
            dataset_id: 数据集 ID

        Returns:
            删除的记录数
        """
        stmt = delete(DataSetsItemsRecord).where(
            DataSetsItemsRecord.dataset_id == dataset_id
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0
