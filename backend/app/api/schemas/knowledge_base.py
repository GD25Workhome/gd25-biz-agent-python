"""
知识库相关 Schema
设计文档：cursor_docs/012803-知识库表与前端查询界面设计.md
"""
from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field


class KnowledgeBaseRecordResponse(BaseModel):
    """知识库单条记录响应，与表字段一致"""

    id: str
    scene_summary: Optional[str] = None
    optimization_question: Optional[str] = None
    reply_example_or_rule: Optional[str] = None
    scene_category: Optional[str] = None
    input_tags: Optional[List[Any]] = None
    response_tags: Optional[List[Any]] = None
    raw_material_full_text: Optional[str] = None
    raw_material_scene_summary: Optional[str] = None
    raw_material_question: Optional[str] = None
    raw_material_answer: Optional[str] = None
    raw_material_other: Optional[str] = None
    technical_tag_classification: Optional[dict] = None
    business_tag_classification: Optional[dict] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class KnowledgeBaseListResponse(BaseModel):
    """知识库列表响应，含 total 与 items，便于前端分页"""

    total: int = Field(description="总条数")
    items: List[KnowledgeBaseRecordResponse] = Field(
        default_factory=list,
        description="当前页数据",
    )
