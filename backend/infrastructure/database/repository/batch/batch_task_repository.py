"""
子任务表仓储（batch_task）
设计文档：cursor_docs/022603-数据embedding批次表字段设计.md
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import AuditBaseRepository
from backend.infrastructure.database.models.batch.batch_task import BatchTaskRecord


class BatchTaskRepository(AuditBaseRepository[BatchTaskRecord]):
    """子任务表仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BatchTaskRecord)

    async def get_by_job_id(
        self,
        job_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BatchTaskRecord]:
        """按 job_id 查询子任务列表（仅未删）。"""
        result = await self.session.execute(
            select(BatchTaskRecord)
            .where(BatchTaskRecord.job_id == job_id)
            .where(self._not_deleted_criterion())
            .order_by(BatchTaskRecord.create_time.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_list(
        self,
        job_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BatchTaskRecord]:
        """分页查询子任务（仅未删）；可选 job_id、status 筛选。"""
        stmt = (
            select(BatchTaskRecord)
            .where(self._not_deleted_criterion())
            .order_by(BatchTaskRecord.create_time.desc())
            .limit(limit)
            .offset(offset)
        )
        if job_id is not None and job_id.strip():
            stmt = stmt.where(BatchTaskRecord.job_id == job_id.strip())
        if status is not None and status.strip():
            stmt = stmt.where(BatchTaskRecord.status == status.strip())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        job_id: str,
        source_table_id: Optional[str] = None,
        source_table_name: Optional[str] = None,
        status: Optional[str] = None,
        runtime_params: Optional[Dict[str, Any]] = None,
        redundant_key: Optional[str] = None,
        **kwargs: Any,
    ) -> BatchTaskRecord:
        """创建子任务记录。审计字段由 AuditBaseRepository.create 自动填充。"""
        return await super().create(
            job_id=job_id,
            source_table_id=source_table_id,
            source_table_name=source_table_name,
            status=status,
            runtime_params=runtime_params,
            redundant_key=redundant_key,
            **kwargs,
        )

    async def update_status(
        self,
        task_id: str,
        status: str,
        execution_result: Optional[str] = None,
        execution_error_message: Optional[str] = None,
        execution_return_key: Optional[str] = None,
    ) -> Optional[BatchTaskRecord]:
        """更新子任务状态及执行结果字段。version、update_time 由基类 update 自动处理。"""
        kwargs: Dict[str, Any] = {"status": status}
        if execution_result is not None:
            kwargs["execution_result"] = execution_result
        if execution_error_message is not None:
            kwargs["execution_error_message"] = execution_error_message
        if execution_return_key is not None:
            kwargs["execution_return_key"] = execution_return_key
        return await self.update(task_id, **kwargs)