"""
导入配置仓储实现
设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
"""
from typing import List, Optional, Tuple
from sqlalchemy import select, func, and_, or_, cast
from sqlalchemy.types import Text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.import_config import ImportConfigRecord


class ImportConfigRepository(BaseRepository[ImportConfigRecord]):
    """导入配置仓储类"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ImportConfigRecord)

    async def get_list_with_total(
        self,
        name: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[ImportConfigRecord], int]:
        """
        分页查询，支持 name（包含）、keyword（在 name/description/import_config 中搜索）。
        """
        conditions = []
        if name and name.strip():
            conditions.append(ImportConfigRecord.name.ilike(f"%{name.strip()}%"))
        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    ImportConfigRecord.name.ilike(kw),
                    ImportConfigRecord.description.ilike(kw),
                    cast(ImportConfigRecord.import_config, Text).ilike(kw),
                )
            )

        base_query = select(ImportConfigRecord)
        count_query = select(func.count()).select_from(ImportConfigRecord)
        if conditions:
            base_query = base_query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        list_query = (
            base_query.order_by(ImportConfigRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(list_query)
        items = list(result.scalars().all())
        return items, total
