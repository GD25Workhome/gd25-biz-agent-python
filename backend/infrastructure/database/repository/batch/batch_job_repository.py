"""
批次表仓储（batch_job）
设计文档：cursor_docs/022603-数据embedding批次表字段设计.md
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import AuditBaseRepository
from backend.infrastructure.database.models.batch.batch_job import BatchJobRecord


class BatchJobRepository(AuditBaseRepository[BatchJobRecord]):
    """批次表仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BatchJobRecord)

    async def get_by_code(self, code: str) -> Optional[BatchJobRecord]:
        """按批次编码查询（仅未删）。"""
        result = await self.session.execute(
            select(BatchJobRecord)
            .where(BatchJobRecord.code == code)
            .where(self._not_deleted_criterion())
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BatchJobRecord]:
        """分页查询批次列表（仅未删）。"""
        result = await self.session.execute(
            select(BatchJobRecord)
            .where(self._not_deleted_criterion())
            .order_by(BatchJobRecord.create_time.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create(
        self,
        code: str,
        total_count: int,
        query_params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> BatchJobRecord:
        """创建批次记录。审计字段由 AuditBaseRepository.create 自动填充。"""
        return await super().create(
            code=code,
            total_count=total_count,
            query_params=query_params,
            **kwargs,
        )
