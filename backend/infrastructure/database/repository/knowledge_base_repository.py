"""
知识库仓储实现
支持按 scene_summary、optimization_question、scene_category、input_tags、response_tags 左模糊查询，分页及 total。
设计文档：cursor_docs/012803-知识库表与前端查询界面设计.md
"""
from typing import List, Optional, Tuple
from sqlalchemy import select, and_, func, cast
from sqlalchemy.types import Text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.knowledge_base import KnowledgeBaseRecord


class KnowledgeBaseRepository(BaseRepository[KnowledgeBaseRecord]):
    """知识库仓储类"""

    def __init__(self, session: AsyncSession):
        """
        初始化知识库仓储

        Args:
            session: 数据库会话
        """
        super().__init__(session, KnowledgeBaseRecord)

    def _build_like_conditions(
        self,
        scene_summary: Optional[str] = None,
        optimization_question: Optional[str] = None,
        scene_category: Optional[str] = None,
        input_tags: Optional[str] = None,
        response_tags: Optional[str] = None,
    ) -> List:
        """
        构建左模糊（LIKE 'keyword%'）条件列表。
        TEXT 字段直接 like；JSONB 字段转为文本后 like。
        """
        conditions = []
        if scene_summary and scene_summary.strip():
            conditions.append(
                KnowledgeBaseRecord.scene_summary.like(
                    scene_summary.strip() + "%"
                )
            )
        if optimization_question and optimization_question.strip():
            conditions.append(
                KnowledgeBaseRecord.optimization_question.like(
                    optimization_question.strip() + "%"
                )
            )
        if scene_category and scene_category.strip():
            conditions.append(
                KnowledgeBaseRecord.scene_category.like(
                    scene_category.strip() + "%"
                )
            )
        if input_tags and input_tags.strip():
            # JSONB 左模糊：转成文本后 LIKE 'keyword%'
            conditions.append(
                cast(
                    KnowledgeBaseRecord.input_tags,
                    Text,
                ).like(input_tags.strip() + "%")
            )
        if response_tags and response_tags.strip():
            conditions.append(
                cast(
                    KnowledgeBaseRecord.response_tags,
                    Text,
                ).like(response_tags.strip() + "%")
            )
        return conditions

    async def get_list_with_total(
        self,
        scene_summary: Optional[str] = None,
        optimization_question: Optional[str] = None,
        scene_category: Optional[str] = None,
        input_tags: Optional[str] = None,
        response_tags: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[KnowledgeBaseRecord], int]:
        """
        分页查询知识库列表，并返回总条数（用于前端分页）。

        Args:
            scene_summary: 场景摘要左模糊
            optimization_question: 优化问题左模糊
            scene_category: 场景分类左模糊
            input_tags: 输入标签左模糊（对 JSONB 序列化文本做 like）
            response_tags: 回复标签左模糊（同上）
            limit: 限制数量
            offset: 偏移量

        Returns:
            (当前页记录列表, 总条数)
        """
        conditions = self._build_like_conditions(
            scene_summary=scene_summary,
            optimization_question=optimization_question,
            scene_category=scene_category,
            input_tags=input_tags,
            response_tags=response_tags,
        )

        base_query = select(KnowledgeBaseRecord)
        if conditions:
            base_query = base_query.where(and_(*conditions))

        # 总条数（同一过滤条件，不含 limit/offset）
        count_query = select(func.count()).select_from(
            KnowledgeBaseRecord
        )
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # 分页列表，按创建时间倒序
        list_query = (
            base_query.order_by(
                KnowledgeBaseRecord.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(list_query)
        items = list(result.scalars().all())

        return items, total
