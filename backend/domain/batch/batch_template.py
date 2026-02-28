"""
批次任务模版：创建模版（CreateTemplate）与执行模版（ExecuteTemplate）。
设计文档：cursor_docs/022701-批次任务创建模版设计方案.md、022803-批次任务执行模版与队列对接技术设计.md
"""
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.batch.dto import (
    BatchTaskExecutionResult,
    BatchTaskQueueItem,
    TaskPreCreateItem,
)
from backend.infrastructure.database.base import generate_ulid
from backend.infrastructure.database.models.batch.batch_job import BatchJobRecord
from backend.infrastructure.database.models.batch.batch_task import BatchTaskRecord
from backend.infrastructure.database.repository.batch.batch_job_repository import (
    BatchJobRepository,
)
from backend.infrastructure.database.repository.batch.batch_task_repository import (
    BatchTaskRepository,
    STATUS_FAILED,
    STATUS_SUCCESS,
)

logger = logging.getLogger(__name__)


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


class ExecuteTemplate(ABC):
    """
    执行批次任务模版：定义「加载 task → 乐观锁 → 业务执行 → 回写结果」流程，子类实现 execute_task_impl。
    任务执行入口统一为 BatchTaskQueueItem。
    """

    def __init__(self, task_repo: BatchTaskRepository) -> None:
        self._task_repo = task_repo

    async def run_one_task(
        self,
        session: AsyncSession,
        item: BatchTaskQueueItem,
    ) -> None:
        """
        模版方法：执行单条任务。入参为队列元素 BatchTaskQueueItem。
        步骤：加载 task → 可选 version 校验 → 乐观锁 pending→running → execute_task_impl → 回写 execution_result/execution_return_key/status 或 execution_error_message/status。
        """
        task_record = await self._task_repo.get_by_id(item.task_id)
        if not task_record:
            logger.error("run_one_task: task 不存在 task_id=%s", item.task_id)
            return

        if getattr(task_record, "version", None) is not None and item.task_version is not None:
            if task_record.version != item.task_version:
                logger.info(
                    "run_one_task: task.version 与队列元素不一致，舍弃 task_id=%s queue_version=%s db_version=%s",
                    item.task_id,
                    item.task_version,
                    task_record.version,
                )
                return

        ok = await self._task_repo.update_status_to_running_if_pending(item.task_id)
        if not ok:
            logger.error(
                "run_one_task: 乐观锁更新 pending→running 失败，跳过执行 task_id=%s",
                item.task_id,
            )
            return

        try:
            result = await self.execute_task_impl(session, task_record)
            execution_return_key = getattr(result, "execution_return_key", None) or ""
            if is_dataclass(result):
                execution_result_str = json.dumps(
                    asdict(result), ensure_ascii=False
                )
            else:
                execution_result_str = json.dumps(
                    {"execution_return_key": execution_return_key},
                    ensure_ascii=False,
                )
            await self._task_repo.update_status(
                item.task_id,
                status=STATUS_SUCCESS,
                execution_result=execution_result_str,
                execution_return_key=execution_return_key,
            )
        except Exception:
            import traceback

            err_msg = traceback.format_exc()
            logger.exception("run_one_task: 业务执行失败 task_id=%s", item.task_id)
            await self._task_repo.update_status(
                item.task_id,
                status=STATUS_FAILED,
                execution_error_message=err_msg[: 64 * 1024],
            )

    @abstractmethod
    async def execute_task_impl(
        self,
        session: AsyncSession,
        task_record: BatchTaskRecord,
    ) -> BatchTaskExecutionResult:
        """
        子类实现：当前任务的业务逻辑。成功时返回标准结果（至少含 execution_return_key），失败时抛出异常。
        """
        ...
