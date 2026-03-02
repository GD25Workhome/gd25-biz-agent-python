"""
批次表仓储（batch_job）
设计文档：cursor_docs/022603-数据embedding批次表字段设计.md、030202-批次任务batch_jobs与Step02清洗批次管理功能对比与缺口分析.md
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.models.batch.batch_job import BatchJobRecord
from backend.infrastructure.database.models.batch.batch_task import BatchTaskRecord
from backend.infrastructure.database.repository.base import AuditBaseRepository
from backend.infrastructure.database.repository.batch.batch_task_repository import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCESS,
)


@dataclass
class BatchJobStatsRow:
    """
    批次 + 子任务统计聚合结果。
    用于列表页展示每批次的 pending/running/success/failed 数量。
    """

    record: BatchJobRecord
    tasks_total: int = 0
    status_pending_count: int = 0
    status_running_count: int = 0
    status_success_count: int = 0
    status_failed_count: int = 0


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
        code: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BatchJobRecord]:
        """分页查询批次列表（仅未删）；支持 code 模糊、job_type 精确筛选。"""
        stmt = (
            select(BatchJobRecord)
            .where(self._not_deleted_criterion())
            .order_by(BatchJobRecord.create_time.desc())
            .limit(limit)
            .offset(offset)
        )
        if code and code.strip():
            stmt = stmt.where(BatchJobRecord.code.ilike(f"%{code.strip()}%"))
        if job_type and job_type.strip():
            stmt = stmt.where(BatchJobRecord.job_type == job_type.strip())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_jobs_with_stats(
        self,
        code: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[BatchJobStatsRow], int]:
        """
        分页查询批次并附带 batch_task 按 status 的统计信息。
        设计文档：cursor_docs/030202。
        """
        count_stmt = select(func.count()).select_from(BatchJobRecord).where(self._not_deleted_criterion())
        if code and code.strip():
            count_stmt = count_stmt.where(BatchJobRecord.code.ilike(f"%{code.strip()}%"))
        if job_type and job_type.strip():
            count_stmt = count_stmt.where(BatchJobRecord.job_type == job_type.strip())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one() or 0

        list_stmt = (
            select(BatchJobRecord)
            .where(self._not_deleted_criterion())
            .order_by(BatchJobRecord.create_time.desc())
            .limit(limit)
            .offset(offset)
        )
        if code and code.strip():
            list_stmt = list_stmt.where(BatchJobRecord.code.ilike(f"%{code.strip()}%"))
        if job_type and job_type.strip():
            list_stmt = list_stmt.where(BatchJobRecord.job_type == job_type.strip())
        records_result = await self.session.execute(list_stmt)
        records = list(records_result.scalars().all())
        if not records:
            return [], total

        job_ids = [r.id for r in records]
        # batch_task 使用 AuditBaseRepository 的 is_deleted
        stats_stmt = (
            select(
                BatchTaskRecord.job_id.label("job_id"),
                func.count(BatchTaskRecord.id).label("tasks_total"),
                func.sum(case((BatchTaskRecord.status == STATUS_PENDING, 1), else_=0)).label("status_pending_count"),
                func.sum(case((BatchTaskRecord.status == STATUS_RUNNING, 1), else_=0)).label("status_running_count"),
                func.sum(case((BatchTaskRecord.status == STATUS_SUCCESS, 1), else_=0)).label("status_success_count"),
                func.sum(case((BatchTaskRecord.status == STATUS_FAILED, 1), else_=0)).label("status_failed_count"),
            )
            .where(BatchTaskRecord.job_id.in_(job_ids))
            .where(BatchTaskRecord.is_deleted == False)  # noqa: E712
            .group_by(BatchTaskRecord.job_id)
        )
        stats_result = await self.session.execute(stats_stmt)
        stats_map: Dict[str, Dict[str, int]] = {}
        for row in stats_result:
            stats_map[row.job_id] = {
                "tasks_total": row.tasks_total or 0,
                "status_pending_count": row.status_pending_count or 0,
                "status_running_count": row.status_running_count or 0,
                "status_success_count": row.status_success_count or 0,
                "status_failed_count": row.status_failed_count or 0,
            }

        def default_stats() -> Dict[str, int]:
            return {
                "tasks_total": 0,
                "status_pending_count": 0,
                "status_running_count": 0,
                "status_success_count": 0,
                "status_failed_count": 0,
            }

        rows = [
            BatchJobStatsRow(
                record=rec,
                tasks_total=stats_map.get(rec.id, default_stats())["tasks_total"],
                status_pending_count=stats_map.get(rec.id, default_stats())["status_pending_count"],
                status_running_count=stats_map.get(rec.id, default_stats())["status_running_count"],
                status_success_count=stats_map.get(rec.id, default_stats())["status_success_count"],
                status_failed_count=stats_map.get(rec.id, default_stats())["status_failed_count"],
            )
            for rec in records
        ]
        return rows, total

    async def create(
        self,
        job_type: str,
        code: str,
        total_count: int,
        query_params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> BatchJobRecord:
        """创建批次记录。需要显式指定 job_type。审计字段由 AuditBaseRepository.create 自动填充。"""
        return await super().create(
            job_type=job_type,
            code=code,
            total_count=total_count,
            query_params=query_params,
            **kwargs,
        )
