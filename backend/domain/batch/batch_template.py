"""
创建批次任务模版
设计文档：cursor_docs/022701-批次任务创建模版设计方案.md
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.base import generate_ulid
from backend.infrastructure.database.repository.batch.batch_job_repository import (
    BatchJobRepository,
)
from backend.infrastructure.database.repository.batch.batch_task_repository import (
    BatchTaskRepository,
)
from backend.infrastructure.database.models.batch.batch_job import BatchJobRecord
from backend.domain.batch.dto import TaskPreCreateItem


class CreateTemplate(ABC):
    """创建批次任务模版：定义「查询 → 生成 code → 组装落库」流程，子类实现查询接口。"""

    def __init__(
        self,
        job_repo: BatchJobRepository,
        task_repo: BatchTaskRepository,
    ) -> None:
        self._job_repo = job_repo
        self._task_repo = task_repo

    async def create_batch(
        self,
        session: AsyncSession,
        query_params: Optional[Dict[str, Any]] = None,
    ) -> BatchJobRecord:
        """
        模版方法：创建批次任务。不可重写整体顺序。
        步骤：1. 查询预创建数据  2. 生成批次 code  3. 取 job_type  4. 组装并持久化 batch_job + batch_task。
        """
        # 1. 子类实现：查询数据，返回预创建 task 列表
        task_items: List[TaskPreCreateItem] = await self.query_tasks_for_pre_create(
            session, query_params
        )
        if not task_items:
            raise ValueError("query_tasks_for_pre_create 返回空列表，无法创建批次")

        # 2. 生成批次 code（模版默认实现，子类可覆盖）
        code = self.generate_batch_code()

        # 3. 子类实现：返回本批次任务类型，供落库及运行阶段按类型路由执行器
        job_type = self.get_job_type()

        # 4. 模版实现：组装 batch_job（含 job_type）、batch_task 并落库
        job = await self._build_and_persist_batch(
            session=session,
            job_type=job_type,
            code=code,
            task_items=task_items,
            query_params=query_params,
        )
        return job

    @abstractmethod
    def get_job_type(self) -> str:
        """
        返回本批次的任务类型（如 embedding、data_clean）。
        子类必须实现；运行阶段将根据 batch_job.job_type 从执行器注册表路由到对应 BatchTaskExecutor。
        """
        ...

    @abstractmethod
    async def query_tasks_for_pre_create(
        self,
        session: AsyncSession,
        query_params: Optional[Dict[str, Any]] = None,
    ) -> List[TaskPreCreateItem]:
        """
        数据查询接口，返回本批次要创建的 task 预创建对象。
        子类必须实现（如查 pipeline_data_items_rewritten 待 embedding 数据）。
        """
        ...

    def generate_batch_code(self) -> str:
        """
        生成批次编码。模版默认实现（如 batch-{ulid}），子类可覆盖以定制规则。
        """
        return f"batch-{generate_ulid()}"

    async def _build_and_persist_batch(
        self,
        session: AsyncSession,
        job_type: str,
        code: str,
        task_items: List[TaskPreCreateItem],
        query_params: Optional[Dict[str, Any]] = None,
    ) -> BatchJobRecord:
        """
        模版内部实现：先创建 batch_job（含 job_type），再逐条创建 batch_task。
        """
        job = await self._job_repo.create(
            job_type=job_type,
            code=code,
            total_count=len(task_items),
            query_params=query_params,
        )
        for item in task_items:
            await self._task_repo.create(
                job_id=job.id,
                source_table_id=item.source_table_id,
                source_table_name=item.source_table_name,
                status="pending",
                runtime_params=item.runtime_params,
                redundant_key=item.redundant_key,
            )
        return job
