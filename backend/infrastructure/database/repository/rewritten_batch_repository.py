"""
Rewritten 批次仓储实现

用于集中管理 rewritten 批次的 batch_code 及元数据。
设计文档：cursor_docs/021101-Rewritten批次表与创建流程设计.md
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.repository.data_items_rewritten_repository import (
    STATUS_FAILED,
    STATUS_INIT,
    STATUS_PROCESSING,
    STATUS_SUCCESS,
)
from backend.infrastructure.database.models.data_items_rewritten import (
    DataItemsRewrittenRecord,
)
from backend.infrastructure.database.models.rewritten_batch import RewrittenBatchRecord


@dataclass
class RewrittenBatchStatsRow:
    """
    批次 + 统计信息聚合结果。

    Attributes:
        record: 批次 ORM 记录
        data_items_total: 实际关联的数据项数量
        status_init_count/status_processing_count/status_success_count/status_failed_count: 各状态数量
    """

    record: RewrittenBatchRecord
    data_items_total: int = 0
    status_init_count: int = 0
    status_processing_count: int = 0
    status_success_count: int = 0
    status_failed_count: int = 0


class RewrittenBatchRepository(BaseRepository[RewrittenBatchRecord]):
    """Rewritten 批次仓储类"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RewrittenBatchRecord)

    async def create(
        self,
        batch_code: str,
        total_count: int,
        create_params: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
    ) -> RewrittenBatchRecord:
        """
        创建批次记录。

        Args:
            batch_code: 批次编码
            total_count: 本批次数据项总量
            create_params: 创建参数（JSON）
            status: 批次级状态（可选）

        Returns:
            创建的 RewrittenBatchRecord
        """
        return await super().create(
            batch_code=batch_code,
            total_count=total_count,
            create_params=create_params,
            status=status,
        )

    async def get_by_batch_code(self, batch_code: str) -> Optional[RewrittenBatchRecord]:
        """按 batch_code 查询单条。"""
        stmt = select(RewrittenBatchRecord).where(
            RewrittenBatchRecord.batch_code == batch_code
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_list(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RewrittenBatchRecord]:
        """
        分页查询批次列表。

        后续可按 create_params->>'dataset_id' 或 JSON 条件筛选，供 UI 使用。
        """
        stmt = (
            select(RewrittenBatchRecord)
            .order_by(RewrittenBatchRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_batches_with_stats(
        self,
        batch_code: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[RewrittenBatchStatsRow], int]:
        """
        分页查询批次并附带 `DataItemsRewrittenRecord` 的统计信息。

        Args:
            batch_code: 支持模糊匹配批次编码
            limit: 每页条数
            offset: 偏移量

        Returns:
            (列表, 总数)，列表元素包含批次记录及统计字段
        """

        conditions = []
        if batch_code and batch_code.strip():
            conditions.append(
                RewrittenBatchRecord.batch_code.ilike(f"%{batch_code.strip()}%")
            )

        count_stmt = select(func.count()).select_from(RewrittenBatchRecord)
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one() or 0

        list_stmt = (
            select(RewrittenBatchRecord)
            .order_by(RewrittenBatchRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if conditions:
            list_stmt = list_stmt.where(*conditions)

        records_result = await self.session.execute(list_stmt)
        records = list(records_result.scalars().all())
        if not records:
            return [], total

        batch_codes = [record.batch_code for record in records if record.batch_code]
        stats_map: Dict[str, Dict[str, int]] = {}
        if batch_codes:
            stats_stmt = (
                select(
                    DataItemsRewrittenRecord.batch_code.label("batch_code"),
                    func.count(DataItemsRewrittenRecord.id).label("data_items_total"),
                    func.sum(
                        case(
                            (DataItemsRewrittenRecord.status == STATUS_INIT, 1),
                            else_=0,
                        )
                    ).label("status_init_count"),
                    func.sum(
                        case(
                            (DataItemsRewrittenRecord.status == STATUS_PROCESSING, 1),
                            else_=0,
                        )
                    ).label("status_processing_count"),
                    func.sum(
                        case(
                            (DataItemsRewrittenRecord.status == STATUS_SUCCESS, 1),
                            else_=0,
                        )
                    ).label("status_success_count"),
                    func.sum(
                        case(
                            (DataItemsRewrittenRecord.status == STATUS_FAILED, 1),
                            else_=0,
                        )
                    ).label("status_failed_count"),
                )
                .where(DataItemsRewrittenRecord.batch_code.in_(batch_codes))
                .group_by(DataItemsRewrittenRecord.batch_code)
            )
            stats_result = await self.session.execute(stats_stmt)
            for row in stats_result:
                stats_map[row.batch_code] = {
                    "data_items_total": row.data_items_total or 0,
                    "status_init_count": row.status_init_count or 0,
                    "status_processing_count": row.status_processing_count or 0,
                    "status_success_count": row.status_success_count or 0,
                    "status_failed_count": row.status_failed_count or 0,
                }

        stats_rows = _compose_batch_stats_rows(records, stats_map)
        return stats_rows, total


def _compose_batch_stats_rows(
    records: Sequence[RewrittenBatchRecord],
    stats_map: Dict[str, Dict[str, int]],
) -> List[RewrittenBatchStatsRow]:
    """将批次记录与统计信息合并，缺失统计时补 0。"""

    def _default_stats() -> Dict[str, int]:
        return {
            "data_items_total": 0,
            "status_init_count": 0,
            "status_processing_count": 0,
            "status_success_count": 0,
            "status_failed_count": 0,
        }

    rows: List[RewrittenBatchStatsRow] = []
    for record in records:
        stats = stats_map.get(record.batch_code or "", _default_stats())
        rows.append(
            RewrittenBatchStatsRow(
                record=record,
                data_items_total=stats["data_items_total"],
                status_init_count=stats["status_init_count"],
                status_processing_count=stats["status_processing_count"],
                status_success_count=stats["status_success_count"],
                status_failed_count=stats["status_failed_count"],
            )
        )
    return rows
