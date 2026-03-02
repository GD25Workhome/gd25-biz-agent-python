"""
子任务表仓储（batch_task）
设计文档：cursor_docs/022603-数据embedding批次表字段设计.md、022803-批次任务执行模版与队列对接技术设计.md
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.models.batch.batch_task import BatchTaskRecord
from backend.infrastructure.database.repository.base import AuditBaseRepository

if TYPE_CHECKING:
    from backend.domain.batch.dto import TaskPreCreateItem

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


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

    async def count_by_job(
        self,
        job_id: str,
        status: Optional[str] = None,
    ) -> int:
        """统计指定 job 下子任务数量（仅未删）；可选 status 筛选。"""
        stmt = select(func.count()).select_from(BatchTaskRecord).where(
            BatchTaskRecord.job_id == job_id.strip()
        ).where(self._not_deleted_criterion())
        if status is not None and status.strip():
            stmt = stmt.where(BatchTaskRecord.status == status.strip())
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

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

    async def create_many(
        self,
        job_id: str,
        items: List[TaskPreCreateItem],
        chunk_size: int = 1000,
    ) -> int:
        """
        批量创建子任务。将 TaskPreCreateItem 转为 kwargs 列表后调用 Base 的 create_many。
        设计文档：cursor_docs/030201-Base批量插入与批次任务创建详细技术设计方案.md

        Args:
            job_id: 批次 job 的 id。
            items: 预创建项列表（来自 CreateTemplate.query_tasks_for_pre_create）。
            chunk_size: 每多少条一组 flush，默认 1000。

        Returns:
            插入条数。
        """
        from backend.domain.batch.dto import TaskPreCreateItem

        dict_list: List[Dict[str, Any]] = [
            {
                "job_id": job_id,
                "source_table_id": item.source_table_id,
                "source_table_name": item.source_table_name,
                "status": STATUS_PENDING,
                "runtime_params": item.runtime_params,
                "redundant_key": item.redundant_key,
            }
            for item in items
        ]
        return await super().create_many(items=dict_list, chunk_size=chunk_size)

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

    async def update_status_to_running_if_pending(self, task_id: str) -> bool:
        """
        仅当 status=pending 时更新为 running，用于执行模版乐观锁。
        复用基类 update(extra_where=...)，保证 version+1、update_time 与乐观锁在同一 UPDATE 中完成。
        设计文档：cursor_docs/022803-批次任务执行模版与队列对接技术设计.md
        :return: 是否更新到行。
        """
        result = await self.update(
            task_id,
            extra_where={"status": STATUS_PENDING},
            status=STATUS_RUNNING,
        )
        return result is not None