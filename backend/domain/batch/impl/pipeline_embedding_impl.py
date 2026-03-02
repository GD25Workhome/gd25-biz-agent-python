"""
Pipeline Embedding 批次任务：创建 Handler 与执行器。

- PipelineEmbeddingCreateHandler：基于 pipeline_data_items_rewritten 创建 Embedding 批次任务。
- PipelineEmbeddingExecutor：根据 task 的 runtime_params 查改写记录，按 embedding_type（Q/QA）拼串并调 embedding 模型，写入 pipeline_embedding_records。

设计文档：cursor_docs/022703、022803、030203-批次任务执行Session拆分改造技术方案.md
"""
from typing import Any, Dict, List, Optional


from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.batch.batch_template import CreateTemplate, ExecuteTemplate
from backend.domain.batch.dto import BatchTaskExecutionResult, TaskPreCreateItem
from backend.domain.batch.exceptions import InvalidJobParamsError
from backend.infrastructure.database.models.batch.batch_task import BatchTaskRecord
from backend.infrastructure.database.repository.data_items_rewritten_repository import (
    DataItemsRewrittenRepository,
    STATUS_FAILED,
    STATUS_INIT,
    STATUS_PROCESSING,
    STATUS_SUCCESS,
)
from backend.infrastructure.database.repository.pipeline.pipeline_embedding_record_repository import (
    PipelineEmbeddingRecordRepository,
)
from backend.infrastructure.llm.embedding_client import EmbeddingClient
from backend.infrastructure.llm.providers.manager import ProviderManager


class PipelineEmbeddingCreateHandler(CreateTemplate):
    """基于改写后数据项创建 Embedding 批次任务的 Handler。"""

    JOB_TYPE: str = "pipeline_embedding"

    def get_job_type(self) -> str:
        """
        返回本 Handler 对应的批次任务类型。

        :return: 固定返回 "pipeline_embedding"。
        """
        return self.JOB_TYPE

    async def query_tasks_for_pre_create(
        self,
        session: AsyncSession,
        query_params: Optional[Dict[str, Any]] = None,
    ) -> List[TaskPreCreateItem]:
        """
        查询需要创建 Embedding 子任务的数据，并转换为 TaskPreCreateItem 列表。

        :param session: SQLAlchemy 异步会话对象。
        :param query_params: 用于筛选改写后数据项的参数字典。
        :return: 子任务预创建数据列表。
        :raises InvalidJobParamsError: 当参数不符合约定（类型、必填项、枚举值等）时抛出。
        """
        params: Dict[str, Any] = query_params or {}
        if not isinstance(params, dict):
            raise InvalidJobParamsError("query_params 必须是对象（JSON object）")

        source_dataset_id = (params.get("source_dataset_id") or "").strip()
        if not source_dataset_id:
            raise InvalidJobParamsError("source_dataset_id 不能为空")

        # 校验 status 枚举值
        raw_status = params.get("status")
        status: Optional[str] = None
        if raw_status is not None and str(raw_status).strip():
            status_str = str(raw_status).strip()
            allowed_status = {
                STATUS_INIT,
                STATUS_PROCESSING,
                STATUS_SUCCESS,
                STATUS_FAILED,
            }
            if status_str not in allowed_status:
                raise InvalidJobParamsError(
                    f"status 非法，仅支持 {', '.join(sorted(allowed_status))}"
                )
            status = status_str

        repo = DataItemsRewrittenRepository(session)
        records = await repo.get_all_for_embedding(
            source_dataset_id=source_dataset_id,
            scenario_description=params.get("scenario_description"),
            rewritten_question=params.get("rewritten_question"),
            rewritten_answer=params.get("rewritten_answer"),
            rewritten_rule=params.get("rewritten_rule"),
            source_item_id=params.get("source_item_id"),
            scenario_type=params.get("scenario_type"),
            sub_scenario_type=params.get("sub_scenario_type"),
            batch_code=params.get("batch_code"),
            trace_id=params.get("trace_id"),
            status=status,
        )

        items: List[TaskPreCreateItem] = []
        for record in records:
            # 冗余键仅使用改写记录 id，便于去重和排查
            redundant_key = str(record.id)

            # 基础运行参数仅保留记录 id，由执行器根据 embedding_type 决定使用哪些字段
            base_params: Dict[str, Any] = {
                "pipeline_data_items_rewritten_id": record.id,
            }

            # 记录 1：基于「场景描述 + 改写问题」进行 Embedding（类型 Q）
            items.append(
                TaskPreCreateItem(
                    source_table_id=record.id,
                    source_table_name="pipeline_data_items_rewritten",
                    runtime_params={
                        **base_params,
                        "embedding_type": "Q",
                    },
                    redundant_key=redundant_key,
                )
            )

            # 记录 2：基于「场景描述 + 改写问答 + 规则」进行 Embedding（类型 QA）
            items.append(
                TaskPreCreateItem(
                    source_table_id=record.id,
                    source_table_name="pipeline_data_items_rewritten",
                    runtime_params={
                        **base_params,
                        "embedding_type": "QA",
                    },
                    redundant_key=redundant_key,
                )
            )

        return items


def _format_embedding_str(
    embedding_type: str,
    scenario_description: str,
    rewritten_question: str,
    rewritten_answer: str,
    rewritten_rule: str,
) -> str:
    """
    按 embedding_type 拼接用于 embedding 的字符串。
    Q：场景描述 + 改写问题；QA：场景描述 + 改写问题 + 改写回答 + 改写规则。
    参考 BeforeEmbeddingFuncNode._format_embedding_str 的拼接方式。
    """
    scenario_description = (scenario_description or "").strip()
    rewritten_question = (rewritten_question or "").strip()
    rewritten_answer = (rewritten_answer or "").strip()
    rewritten_rule = (rewritten_rule or "").strip()

    _indent = "    "  # 缩进
    parts = []
    if scenario_description:
        parts.append("场景描述：\n" + _indent + scenario_description)
    if rewritten_question:
        parts.append("问题：\n" + _indent + rewritten_question)
    if embedding_type == "QA":
        if rewritten_answer:
            parts.append("回复：\n" + _indent + rewritten_answer)
        if rewritten_rule:
            parts.append("规则：\n" + _indent + rewritten_rule)
    return "\n".join(parts)


class PipelineEmbeddingExecutor(ExecuteTemplate):
    """
    Pipeline Embedding 执行器：查改写记录 → 拼串 → 调 embedding 模型 → 写 pipeline_embedding_records。
    设计文档：030203，execute_task_impl 内开短 session 做 DB 读写。
    """

    def __init__(self, session_factory: Any) -> None:
        """
        :param session_factory: 会话工厂（如 get_session_factory()），供 execute_task_impl 内开短 session 使用。
        """
        self._session_factory = session_factory

    def _get_embedding_client(self) -> EmbeddingClient:
        """获取豆包 embedding 客户端（与 flow 中 embedding 节点配置一致）。"""
        provider = "doubao-embedding"
        config = ProviderManager.get_provider(provider)
        model = getattr(config, "default_model", None) or "doubao-embedding-vision-250615"
        return EmbeddingClient(provider=provider, model=model)

    async def execute_task_impl(
        self,
        task_record: BatchTaskRecord,
    ) -> BatchTaskExecutionResult:
        runtime_params: Dict[str, Any] = (task_record.runtime_params or {}) or {}
        rewritten_id = runtime_params.get("pipeline_data_items_rewritten_id")
        embedding_type = (runtime_params.get("embedding_type") or "Q").strip().upper() or "Q"
        if embedding_type not in ("Q", "QA"):
            embedding_type = "Q"

        if not rewritten_id:
            raise ValueError("runtime_params 中缺少 pipeline_data_items_rewritten_id")

        async with self._session_factory() as session:
            rewritten_repo = DataItemsRewrittenRepository(session)
            rewritten = await rewritten_repo.get_by_id(rewritten_id)
            if not rewritten:
                raise ValueError(f"改写记录不存在: pipeline_data_items_rewritten_id={rewritten_id}")

            embedding_str = _format_embedding_str(
                embedding_type=embedding_type,
                scenario_description=rewritten.scenario_description or "",
                rewritten_question=rewritten.rewritten_question or "",
                rewritten_answer=rewritten.rewritten_answer or "",
                rewritten_rule=rewritten.rewritten_rule or "",
            )
            if not embedding_str.strip():
                raise ValueError("拼接后的 embedding 字符串为空")

            client = self._get_embedding_client()
            vectors = client.embed_documents([embedding_str])
            embedding_value = vectors[0] if vectors else None
            if not embedding_value:
                raise ValueError("embedding 模型返回为空")

            embed_repo = PipelineEmbeddingRecordRepository(session)
            record = await embed_repo.create(
                embedding_str=embedding_str,
                embedding_value=embedding_value,
                embedding_type=embedding_type,
                is_published=False,
                type_=getattr(rewritten, "scenario_type", None) or None,
                sub_type=getattr(rewritten, "sub_scenario_type", None) or None,
                metadata_=None,
            )
            await session.commit()
            return BatchTaskExecutionResult(execution_return_key=record.id)
