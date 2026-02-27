"""
数据集合仓储实现
支持按 path_id、name、keyword 筛选，分页、total。
设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
"""
from typing import List, Optional, Tuple
from sqlalchemy import select, func, and_, or_, cast
from sqlalchemy.types import Text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.data_sets import DataSetsRecord


class DataSetsRepository(BaseRepository[DataSetsRecord]):
    """数据集合仓储类"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DataSetsRecord)

    async def get_list_with_total(
        self,
        path_id: Optional[str] = None,
        name: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[DataSetsRecord], int]:
        """
        分页查询，支持 path_id、name（包含）、keyword（在 input_schema/output_schema/metadata 中搜索）。
        """
        conditions = []
        if path_id is not None:
            conditions.append(DataSetsRecord.path_id == path_id)
        if name and name.strip():
            conditions.append(DataSetsRecord.name.ilike(f"%{name.strip()}%"))
        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    cast(DataSetsRecord.input_schema, Text).ilike(kw),
                    cast(DataSetsRecord.output_schema, Text).ilike(kw),
                    cast(DataSetsRecord.metadata_, Text).ilike(kw),
                )
            )

        base_query = select(DataSetsRecord)
        count_query = select(func.count()).select_from(DataSetsRecord)
        if conditions:
            base_query = base_query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        list_query = (
            base_query.order_by(DataSetsRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(list_query)
        items = list(result.scalars().all())
        return items, total
