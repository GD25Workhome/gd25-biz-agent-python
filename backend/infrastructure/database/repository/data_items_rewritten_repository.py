"""
改写后数据项仓储实现
支持按场景描述、改写后问题/回答/规则、来源 ID、场景类型等筛选，分页、total。
设计文档：doc/总体设计规划/数据归档-schema/Step2-数据初步筛选.md
技术设计：cursor_docs/021001-Rewritten流程批量异步执行技术设计.md
"""
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.data_items_rewritten import DataItemsRewrittenRecord
from backend.infrastructure.database.models.data_sets_items import DataSetsItemsRecord

# 状态常量（与设计文档 5.3.2.1 一致）
STATUS_INIT = "init"
STATUS_PROCESSING = "processing"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


def _add_ilike_condition(conditions: list, field, value: Optional[str]) -> None:
    """若 value 非空，添加 ilike 模糊匹配条件"""
    if value and value.strip():
        conditions.append(field.ilike(f"%{value.strip()}%"))


class DataItemsRewrittenRepository(BaseRepository[DataItemsRewrittenRecord]):
    """改写后数据项仓储类"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DataItemsRewrittenRecord)

    async def get_list_with_total(
        self,
        scenario_description: Optional[str] = None,
        rewritten_question: Optional[str] = None,
        rewritten_answer: Optional[str] = None,
        rewritten_rule: Optional[str] = None,
        source_dataset_id: Optional[str] = None,
        source_item_id: Optional[str] = None,
        scenario_type: Optional[str] = None,
        sub_scenario_type: Optional[str] = None,
        batch_code: Optional[str] = None,
        trace_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[DataItemsRewrittenRecord], int]:
        """
        分页查询，支持场景描述、改写后问题/回答/规则、来源 ID、场景类型、子场景类型、
        批次code、traceId、执行状态筛选。文本字段使用 ilike 模糊匹配，status 精确匹配。
        """
        conditions = []
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.scenario_description,
            scenario_description,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.rewritten_question,
            rewritten_question,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.rewritten_answer,
            rewritten_answer,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.rewritten_rule,
            rewritten_rule,
        )
        # 来源 dataSetsId、dataItemsId 使用精确匹配
        if source_dataset_id and source_dataset_id.strip():
            conditions.append(
                DataItemsRewrittenRecord.source_dataset_id == source_dataset_id.strip()
            )
        if source_item_id and source_item_id.strip():
            conditions.append(
                DataItemsRewrittenRecord.source_item_id == source_item_id.strip()
            )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.scenario_type,
            scenario_type,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.sub_scenario_type,
            sub_scenario_type,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.batch_code,
            batch_code,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.trace_id,
            trace_id,
        )
        if status and status.strip():
            conditions.append(
                DataItemsRewrittenRecord.status == status.strip()
            )

        base_query = select(DataItemsRewrittenRecord)
        count_query = select(func.count()).select_from(DataItemsRewrittenRecord)
        if conditions:
            base_query = base_query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        list_query = (
            base_query.order_by(DataItemsRewrittenRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(list_query)
        items = list(result.scalars().all())
        return items, total

    async def get_all_for_embedding(
        self,
        *,
        source_dataset_id: str,
        scenario_description: Optional[str] = None,
        rewritten_question: Optional[str] = None,
        rewritten_answer: Optional[str] = None,
        rewritten_rule: Optional[str] = None,
        source_item_id: Optional[str] = None,
        scenario_type: Optional[str] = None,
        sub_scenario_type: Optional[str] = None,
        batch_code: Optional[str] = None,
        trace_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[DataItemsRewrittenRecord]:
        """
        无分页查询，用于 Embedding 批次任务创建场景。

        筛选条件语义与 get_list_with_total 一致，只是去掉了 limit/offset，
        并按 created_at 升序返回全部命中的记录。
        """
        if not source_dataset_id or not source_dataset_id.strip():
            # 由上层 Handler 保证必填，这里防御性返回空列表，避免误查全部数据。
            return []

        conditions = []
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.scenario_description,
            scenario_description,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.rewritten_question,
            rewritten_question,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.rewritten_answer,
            rewritten_answer,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.rewritten_rule,
            rewritten_rule,
        )
        # 来源 dataSetsId、dataItemsId 使用精确匹配
        conditions.append(
            DataItemsRewrittenRecord.source_dataset_id == source_dataset_id.strip()
        )
        if source_item_id and source_item_id.strip():
            conditions.append(
                DataItemsRewrittenRecord.source_item_id == source_item_id.strip()
            )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.scenario_type,
            scenario_type,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.sub_scenario_type,
            sub_scenario_type,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.batch_code,
            batch_code,
        )
        _add_ilike_condition(
            conditions,
            DataItemsRewrittenRecord.trace_id,
            trace_id,
        )
        if status and status.strip():
            conditions.append(DataItemsRewrittenRecord.status == status.strip())

        stmt = (
            select(DataItemsRewrittenRecord)
            .where(and_(*conditions))
            .order_by(DataItemsRewrittenRecord.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_source_item_id(
        self,
        source_item_id: str,
    ) -> Optional[DataItemsRewrittenRecord]:
        """按 source_item_id 查询单条（一个原始项可能对应一条改写结果）。"""
        stmt = select(DataItemsRewrittenRecord).where(
            DataItemsRewrittenRecord.source_item_id == source_item_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_source_ids(
        self,
        source_dataset_id: str,
        source_item_id: str,
    ) -> Optional[DataItemsRewrittenRecord]:
        """按 source_dataset_id + source_item_id 查询单条，供 update_rewritten_data_func 使用。"""
        stmt = select(DataItemsRewrittenRecord).where(
            and_(
                DataItemsRewrittenRecord.source_dataset_id == source_dataset_id,
                DataItemsRewrittenRecord.source_item_id == source_item_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_init_batch(
        self,
        records: List[DataSetsItemsRecord],
        batch_code: str,
        dataset_id: str,
    ) -> int:
        """
        批量创建 init 记录，返回创建数量。
        每条记录：source_dataset_id=dataset_id, source_item_id=record.id, status=init, batch_code=batch_code。
        若 DataItemsRewritten 中已存在相同 source_dataset_id、source_item_id 且 status 为 init/processing/success 的记录，则跳过，避免重复下发改写任务。
        """
        if not records:
            return 0
        ids = [rec.id for rec in records]
        # 批量查询：已存在 init/processing/success 的 source_item_id 集合
        stmt = select(DataItemsRewrittenRecord.source_item_id).where(
            and_(
                DataItemsRewrittenRecord.source_dataset_id == dataset_id,
                DataItemsRewrittenRecord.source_item_id.in_(ids),
                DataItemsRewrittenRecord.status.in_(
                    [STATUS_INIT, STATUS_PROCESSING, STATUS_SUCCESS]
                ),
            )
        )
        result = await self.session.execute(stmt)
        existing_ids = set(result.scalars().all())
        created = 0
        for rec in records:
            if rec.id in existing_ids:
                continue
            await self.create(
                source_dataset_id=dataset_id,
                source_item_id=rec.id,
                status=STATUS_INIT,
                batch_code=batch_code,
            )
            created += 1
        return created

    async def get_pending_by_batch_code(
        self,
        batch_code: str,
    ) -> List[DataItemsRewrittenRecord]:
        """
        按批次获取待执行任务：status in (init, processing)。
        用于「运行」时入队，包含上次中断的 processing 记录。
        设计文档：cursor_docs/021105-Step02批次任务队列与运行停止技术设计.md
        """
        if not batch_code or not batch_code.strip():
            return []
        conditions = [
            DataItemsRewrittenRecord.batch_code == batch_code.strip(),
            DataItemsRewrittenRecord.status.in_([STATUS_INIT, STATUS_PROCESSING]),
            DataItemsRewrittenRecord.source_dataset_id.isnot(None),
            DataItemsRewrittenRecord.source_dataset_id != "",
            DataItemsRewrittenRecord.source_item_id.isnot(None),
            DataItemsRewrittenRecord.source_item_id != "",
        ]
        stmt = (
            select(DataItemsRewrittenRecord)
            .where(and_(*conditions))
            .order_by(DataItemsRewrittenRecord.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_init_records(
        self,
        limit: int = 10,
        batch_code: Optional[str] = None,
    ) -> List[DataItemsRewrittenRecord]:
        """
        拉取 status=init 的记录，按 created_at 升序。
        子方案 B 下，拉取后由 Worker 调用 update_status 置为 processing。
        """
        conditions = [
            DataItemsRewrittenRecord.status == STATUS_INIT,
            DataItemsRewrittenRecord.source_dataset_id.isnot(None),
            DataItemsRewrittenRecord.source_dataset_id != "",
            DataItemsRewrittenRecord.source_item_id.isnot(None),
            DataItemsRewrittenRecord.source_item_id != "",
        ]
        stmt = (
            select(DataItemsRewrittenRecord)
            .where(and_(*conditions))
            .order_by(DataItemsRewrittenRecord.created_at.asc())
            .limit(limit)
        )
        if batch_code and batch_code.strip():
            stmt = stmt.where(
                DataItemsRewrittenRecord.batch_code == batch_code.strip()
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        record_id: str,
        status: str,
        execution_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """更新记录的 status，失败时可写入 execution_metadata。"""
        values: Dict[str, Any] = {"status": status}
        if execution_metadata is not None:
            values["execution_metadata"] = execution_metadata
        stmt = (
            update(DataItemsRewrittenRecord)
            .where(DataItemsRewrittenRecord.id == record_id)
            .values(**values)
        )
        result = await self.session.execute(stmt)
        return (result.rowcount or 0) > 0

    async def update_status_to_processing_if_init(
        self,
        record_id: str,
        execution_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        仅当 status=init 时更新为 processing，用于消费者防重。
        返回是否更新到行（rowcount>0）。
        设计文档：cursor_docs/021201-Rewritten队列与任务状态重构技术设计.md
        """
        values: Dict[str, Any] = {"status": STATUS_PROCESSING}
        if execution_metadata is not None:
            values["execution_metadata"] = execution_metadata
        stmt = (
            update(DataItemsRewrittenRecord)
            .where(
                DataItemsRewrittenRecord.id == record_id,
                DataItemsRewrittenRecord.status == STATUS_INIT,
            )
            .values(**values)
        )
        result = await self.session.execute(stmt)
        return (result.rowcount or 0) > 0
