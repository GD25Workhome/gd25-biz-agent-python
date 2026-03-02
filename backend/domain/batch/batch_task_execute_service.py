"""
批次任务执行服务：按 job_type 解析执行器并执行单条任务。
设计文档：cursor_docs/022803-批次任务执行模版与队列对接技术设计.md、030203-批次任务执行Session拆分改造技术方案.md
"""
from typing import Any, Callable, Dict

from backend.domain.batch.batch_template import ExecuteTemplate
from backend.domain.batch.dto import BatchTaskQueueItem
from backend.domain.batch.exceptions import UnknownJobTypeError

# 与创建侧 JOB_TYPE 保持一致
JOB_TYPE_PIPELINE_EMBEDDING = "pipeline_embedding"

# session_factory 为可创建 AsyncSession 的工厂（如 get_session_factory() 的返回值）
ExecutorFactory = Callable[[Any], ExecuteTemplate]


class BatchTaskExecuteService:
    """
    根据队列元素的 job_type 从注册表获取执行器，并委托 run_one_task。
    设计文档：030203，传入 session_factory，执行器内部两段短 session。
    """

    def __init__(self) -> None:
        self._registry: Dict[str, ExecutorFactory] = {
            JOB_TYPE_PIPELINE_EMBEDDING: self._create_pipeline_embedding_executor,
        }

    async def run_one_batch_task(
        self,
        session_factory: Any,
        item: BatchTaskQueueItem,
    ) -> None:
        """
        按 item.job_type 取执行器并执行单条任务。commit 在模版内两段 session 各自完成。
        :raises UnknownJobTypeError: 当 job_type 未注册时抛出。
        """
        factory = self._registry.get((item.job_type or "").strip())
        if factory is None:
            raise UnknownJobTypeError(item.job_type or "")
        executor = factory(session_factory)
        await executor.run_one_task(session_factory, item)

    def _create_pipeline_embedding_executor(
        self,
        session_factory: Any,
    ) -> ExecuteTemplate:
        from backend.domain.batch.impl.pipeline_embedding_impl import (
            PipelineEmbeddingExecutor,
        )

        return PipelineEmbeddingExecutor(session_factory=session_factory)
