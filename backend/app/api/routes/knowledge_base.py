"""
知识库列表查询路由
设计文档：cursor_docs/012803-知识库表与前端查询界面设计.md
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.knowledge_base import (
    KnowledgeBaseRecordResponse,
    KnowledgeBaseListResponse,
)
from backend.infrastructure.database.connection import get_async_session
from backend.infrastructure.database.repository.knowledge_base_repository import (
    KnowledgeBaseRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/knowledge-base", response_model=KnowledgeBaseListResponse)
async def list_knowledge_base(
    scene_summary: Optional[str] = Query(
        None, description="场景摘要左模糊"
    ),
    optimization_question: Optional[str] = Query(
        None, description="优化问题左模糊"
    ),
    scene_category: Optional[str] = Query(
        None, description="场景分类左模糊"
    ),
    input_tags: Optional[str] = Query(
        None, description="输入标签左模糊"
    ),
    response_tags: Optional[str] = Query(
        None, description="回复标签左模糊"
    ),
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_async_session),
):
    """
    查询知识库列表（分页 + 左模糊）。

    Query 参数与设计文档 4.2、4.3 一致；返回 total 与 items 供前端分页。
    """
    try:
        repo = KnowledgeBaseRepository(session)
        items, total = await repo.get_list_with_total(
            scene_summary=scene_summary,
            optimization_question=optimization_question,
            scene_category=scene_category,
            input_tags=input_tags,
            response_tags=response_tags,
            limit=limit,
            offset=offset,
        )
        await session.commit()
        return KnowledgeBaseListResponse(
            total=total,
            items=[KnowledgeBaseRecordResponse.model_validate(r) for r in items],
        )
    except Exception as e:
        await session.rollback()
        logger.error("查询知识库列表失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")
