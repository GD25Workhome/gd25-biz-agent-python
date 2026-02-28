"""
Pipeline Embedding 记录表仓储（pipeline_embedding_records）
设计文档：cursor_docs/022801-pipeline_embedding_records表与model-repository技术设计.md
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import AuditBaseRepository
from backend.infrastructure.database.models.pipeline.pipeline_embedding_record import (
    PipelineEmbeddingRecordRecord,
)


class PipelineEmbeddingRecordRepository(
    AuditBaseRepository[PipelineEmbeddingRecordRecord],
):
    """Pipeline Embedding 记录表仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PipelineEmbeddingRecordRecord)

    async def get_list(
        self,
        limit: int = 100,
        offset: int = 0,
        type_: Optional[str] = None,
        sub_type: Optional[str] = None,
        is_published: Optional[bool] = None,
    ) -> List[PipelineEmbeddingRecordRecord]:
        """分页查询列表（仅未删）；可选 type_、sub_type、is_published 筛选，按 create_time 倒序。"""
        stmt = (
            select(PipelineEmbeddingRecordRecord)
            .where(self._not_deleted_criterion())
            .order_by(PipelineEmbeddingRecordRecord.create_time.desc())
            .limit(limit)
            .offset(offset)
        )
        if type_ is not None and type_.strip():
            stmt = stmt.where(PipelineEmbeddingRecordRecord.type_ == type_.strip())
        if sub_type is not None and sub_type.strip():
            stmt = stmt.where(
                PipelineEmbeddingRecordRecord.sub_type == sub_type.strip()
            )
        if is_published is not None:
            stmt = stmt.where(
                PipelineEmbeddingRecordRecord.is_published == is_published
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        embedding_str: Optional[str] = None,
        embedding_value: Any = None,
        embedding_type: Optional[str] = None,
        is_published: bool = False,
        type_: Optional[str] = None,
        sub_type: Optional[str] = None,
        metadata_: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> PipelineEmbeddingRecordRecord:
        """创建 Pipeline Embedding 记录。审计字段由 AuditBaseRepository.create 自动填充。"""
        return await super().create(
            embedding_str=embedding_str,
            embedding_value=embedding_value,
            embedding_type=embedding_type,
            is_published=is_published,
            type_=type_,
            sub_type=sub_type,
            metadata_=metadata_,
            **kwargs,
        )
