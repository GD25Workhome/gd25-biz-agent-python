"""
Embedding 批次任务创建 Handler。

基于 pipeline_data_items_rewritten 表的数据，为指定筛选条件创建 Embedding 批次任务。

设计文档：cursor_docs/022703-批次任务通用创建接口技术设计.md
"""
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.batch.batch_template import CreateTemplate
from backend.domain.batch.dto import TaskPreCreateItem
from backend.domain.batch.exceptions import InvalidJobParamsError
from backend.infrastructure.database.repository.data_items_rewritten_repository import (
    DataItemsRewrittenRepository,
    STATUS_FAILED,
    STATUS_INIT,
    STATUS_PROCESSING,
    STATUS_SUCCESS,
)


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
