"""
华院五维画像评分 Schema（对接 exhibition /huayuan/portrait）
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

PortraitTier = Literal["strong", "stronger", "medium", "weak_or_unknown"]
FactStatus = Literal["confirmed", "inferred", "unknown"]
DimCode = Literal[
    "biz_complexity",
    "update_freq",
    "budget",
    "intel_potential",
    "benchmark",
]

REQUIRED_DIM_CODES: List[str] = [
    "biz_complexity",
    "update_freq",
    "budget",
    "intel_potential",
    "benchmark",
]

DEFAULT_PORTRAIT_MAX_DOCS = 20
DEFAULT_PORTRAIT_MAX_LOAD_TIMES = 3


class PortraitKnowledgeConfig(BaseModel):
    """画像知识库开关（缺省 enabled=true）。"""

    enabled: bool = Field(default=True, description="是否 Milvus 召回；false 时仅 candidate_docs")
    max_docs: Optional[int] = Field(default=None, description="召回+补漏上限")
    max_load_times: Optional[int] = Field(default=None, description="load_news_document 次数上限")
    prefer_source_kinds: List[str] = Field(
        default_factory=list,
        description="优先 source_kind 过滤（Milvus）",
    )


class PortraitCandidateDoc(BaseModel):
    """Java 补漏候选文档。"""

    doc_id: Union[int, str]
    title: Optional[str] = None
    summary: Optional[str] = None
    url: Optional[str] = None
    source_kind: Optional[str] = None
    content_grade: Optional[str] = Field(default="full")


class PortraitCitation(BaseModel):
    """单条外部引用。"""

    source_type: str = Field(..., description="knowledge_base | web | rule_prefill")
    doc_id: Optional[Union[int, str]] = None
    title: Optional[str] = None
    url: Optional[str] = None
    source_kind: Optional[str] = None
    content_grade: Optional[str] = None
    quote: Optional[str] = None
    cite_reason: Optional[str] = None


class PortraitScoreItem(BaseModel):
    """单维 score_item。"""

    code: str
    tier: str
    fact_status: str = Field(default="unknown")
    score_reason: str = Field(default="")
    citations: List[PortraitCitation] = Field(default_factory=list)
    missing_reason: Optional[str] = None


class PortraitResult(BaseModel):
    """Agent 输出的画像结构（score_items）。"""

    score_items: List[PortraitScoreItem] = Field(default_factory=list)
    loaded_doc_ids: List[str] = Field(default_factory=list)
    discarded_doc_ids: List[str] = Field(default_factory=list)
    load_count: int = Field(default=0, ge=0)
    kb_hit_count: int = Field(default=0, ge=0)
    kb_load_count: int = Field(default=0, ge=0)


class HuayuanPortraitRequestContext(BaseModel):
    """请求中的 context 对象。"""

    profile_job_id: Optional[int] = None
    rule_version: Optional[str] = None
    company: Optional[Dict[str, Any]] = None
    rule_prefill: Optional[Dict[str, Any]] = None
    knowledge: Optional[PortraitKnowledgeConfig] = None
    candidate_docs: List[PortraitCandidateDoc] = Field(default_factory=list)
    file_ids: List[str] = Field(default_factory=list, description="遗留；映射为 candidate_docs")
    file_metas: List[Dict[str, Any]] = Field(default_factory=list)
    stats: Optional[Dict[str, Any]] = None
    max_load_times: Optional[int] = Field(default=None, description="建议最大加载次数")
    document_tool_base_url: Optional[str] = Field(
        default=None,
        description="已废弃；load 走 MySQL 直读",
    )

    @field_validator("file_ids", mode="before")
    @classmethod
    def coerce_file_ids(cls, value: Any) -> List[str]:
        """将 file_ids 统一转为字符串列表。"""
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("file_ids 必须是数组")
        return [str(x).strip() for x in value if str(x).strip()]


class HuayuanPortraitRequest(BaseModel):
    """华院画像评分请求。"""

    query: str = Field(..., description="评分任务提示")
    context: HuayuanPortraitRequestContext = Field(..., description="无全文的业务上下文")
    trace_id: Optional[str] = Field(default=None, description="可选 Trace ID")

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        """
            校验 query 非空。

            Args:
                value: 原始 query

            Returns:
                去空白后的 query

            Raises:
                ValueError: query 为空
        """
        stripped = value.strip() if isinstance(value, str) else ""
        if not stripped:
            raise ValueError("query 不能为空")
        return stripped


class HuayuanPortraitResponse(BaseModel):
    """华院画像评分响应。"""

    trace_id: str = Field(..., description="本次 Trace ID")
    portrait: PortraitResult = Field(..., description="画像候选结果")
    response: Optional[str] = Field(
        default=None, description="可选：portrait 的 JSON 字符串，便于人工查看"
    )
