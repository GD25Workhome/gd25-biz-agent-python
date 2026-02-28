"""
批次任务执行服务：按 job_type 解析执行器并执行单条任务。
设计文档：cursor_docs/022803-批次任务执行模版与队列对接技术设计.md
"""
from typing import Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.batch.batch_template import ExecuteTemplate
from backend.domain.batch.dto import BatchTaskQueueItem
from backend.domain.batch.exceptions import UnknownJobTypeError
from backend.infrastructure.database.repository.batch.batch_task_repository import (
    BatchTaskRepository,
)

# 与创建侧 JOB_TYPE 保持一致
JOB_TYPE_PIPELINE_EMBEDDING = "pipeline_embedding"

ExecutorFactory = Callable[[AsyncSession], ExecuteTemplate]


class BatchTaskExecuteService:
    """
    根据队列元素的 job_type 从注册表获取执行器，并委托 run_one_task。
    """

    def __init__(self) -> None:
        self._registry: Dict[str, ExecutorFactory] = {
            JOB_TYPE_PIPELINE_EMBEDDING: self._create_pipeline_embedding_executor,
        }

    async def run_one_batch_task(
        self,
        session: AsyncSession,
        item: BatchTaskQueueItem,
    ) -> None:
        """
        按 item.job_type 取执行器并执行单条任务。
        :raises UnknownJobTypeError: 当 job_type 未注册时抛出。
        """
        factory = self._registry.get((item.job_type or "").strip())
        if factory is None:
            raise UnknownJobTypeError(item.job_type or "")
        executor = factory(session)
        await executor.run_one_task(session, item)

    def _create_pipeline_embedding_executor(
        self,
        session: AsyncSession,
    ) -> ExecuteTemplate:
        from backend.domain.batch.impl.pipeline_embedding_impl import (
            PipelineEmbeddingExecutor,
        )

        task_repo = BatchTaskRepository(session)
        return PipelineEmbeddingExecutor(task_repo=task_repo)
