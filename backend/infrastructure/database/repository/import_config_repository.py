"""
导入配置仓储实现
设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
"""
from typing import List, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.import_config import ImportConfigRecord


class ImportConfigRepository(BaseRepository[ImportConfigRecord]):
    """导入配置仓储类"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ImportConfigRecord)

    async def get_list_with_total(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[ImportConfigRecord], int]:
        """获取配置列表及总条数。"""
        count_stmt = select(func.count()).select_from(ImportConfigRecord)
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = (
            select(ImportConfigRecord)
            .order_by(ImportConfigRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        return items, total
