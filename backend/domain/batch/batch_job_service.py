"""
批次任务创建服务。

负责维护 job_type 到具体批次创建 Handler 的映射，并提供统一的创建入口。

设计文档：cursor_docs/022703-批次任务通用创建接口技术设计.md
"""
from typing import Any, Callable, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.models.batch.batch_job import BatchJobRecord
from backend.infrastructure.database.repository.batch.batch_job_repository import (
    BatchJobRepository,
)
from backend.infrastructure.database.repository.batch.batch_task_repository import (
    BatchTaskRepository,
)
from backend.domain.batch.create_template import BatchCreateTemplate
from backend.domain.batch.exceptions import InvalidJobParamsError, UnknownJobTypeError
from backend.domain.batch.pipeline_embedding_batch_handler import (
    PipelineEmbeddingBatchHandler,
)

HandlerFactory = Callable[[AsyncSession], BatchCreateTemplate]

# 目前仅定义 Embedding 批次 job_type，后续可在此处扩展更多类型
JOB_TYPE_PIPELINE_EMBEDDING = "pipeline_embedding"


class BatchJobCreateService:
    """
    批次任务创建服务。

    根据 job_type 从注册表中获取对应的 Handler，并委托其完成批次任务创建。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        初始化服务。

        :param session: SQLAlchemy 异步会话对象，同一生命周期内复用。
        """
        self._session = session
        self._registry: Dict[str, HandlerFactory] = {
            JOB_TYPE_PIPELINE_EMBEDDING: self._create_pipeline_embedding_handler,
        }

    async def create_batch(
        self,
        job_type: str,
        query_params: Optional[Dict[str, Any]] = None,
    ) -> BatchJobRecord:
        """
        创建批次任务。

        :param job_type: 批次任务类型，用于从注册表中查找具体 Handler。
        :param query_params: 与 job_type 对应的筛选 / 创建参数对象。
        :return: 新创建的 batch_job 记录。
        :raises InvalidJobParamsError: 当 job_type 为空时抛出。
        :raises UnknownJobTypeError: 当 job_type 未在注册表中注册时抛出。
        """
        normalized_job_type = (job_type or "").strip()
        if not normalized_job_type:
            raise InvalidJobParamsError("job_type 不能为空")

        factory = self._registry.get(normalized_job_type)
        if factory is None:
            raise UnknownJobTypeError(normalized_job_type)

        handler = factory(self._session)
        job = await handler.create_batch(
            session=self._session,
            query_params=query_params or {},
        )
        return job

    def _create_pipeline_embedding_handler(
        self,
        session: AsyncSession,
    ) -> BatchCreateTemplate:
        """
        创建 PipelineEmbeddingBatchHandler 实例。

        :param session: SQLAlchemy 异步会话对象。
        :return: 批次创建模版子类实例。
        """
        job_repo = BatchJobRepository(session)
        task_repo = BatchTaskRepository(session)
        return PipelineEmbeddingBatchHandler(job_repo=job_repo, task_repo=task_repo)

