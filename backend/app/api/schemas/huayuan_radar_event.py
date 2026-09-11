"""
华院规则二：展厅项目需求评分 Schema（对接 /huayuan/radar-event-score）
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


SubjectConfidence = Literal["high", "medium", "low", "unknown"]
FactStatus = Literal["confirmed", "inferred", "unknown", "conflict"]
AdmissionHint = Literal["pass", "reject_unrelated", "pending_verify", "expired"]
AuthorityTier = Literal[
    "regulator_or_exchange",
    "gov",
    "company_official",
    "media",
    "ugc_or_noise",
    "unknown",
]

# 产品 §3.4 合法离散分值
VALID_EVIDENCE_SCORES = {85, 75, 60, 45, 25, 10}
VALID_SPECIFICITY_SCORES = {15, 10, 5, 0}

# 分工具默认配额（效果优先；联调稳定后可收紧）
DEFAULT_MAX_BOCHA = 10
DEFAULT_MAX_ANYSEARCH = 10
# 兼容旧字段：未传分工具限额时，用 max_search_times 同时作为两工具上限
DEFAULT_MAX_SEARCH_TIMES = 10
DEFAULT_MAX_EXTRACT_TIMES = 8
DEFAULT_MAX_RESULTS_PER_SEARCH = 5
DEFAULT_QUERY_HINT = (
    "展厅/展馆/展示中心/体验中心/长期展示空间等需求与招采、立项、改造信号"
)


class RadarEventEvidenceItem(BaseModel):
    """单条可追溯证据。"""

    title: Optional[str] = Field(default=None, description="标题")
    summary: Optional[str] = Field(default=None, description="摘要")
    quote: Optional[str] = Field(default=None, description="短摘录，建议≤200字")
    url: Optional[str] = Field(default=None, description="原文 URL")
    publish_date: Optional[str] = Field(default=None, description="发布日期（原文表述）")
    source_host: Optional[str] = Field(default=None, description="来源主机")
    authority_tier: Optional[str] = Field(default=None, description="启发式权威档")
    kept: bool = Field(default=True, description="是否纳入计分证据")


class RadarEventDiscardedItem(BaseModel):
    """被排除的命中结果。"""

    title: Optional[str] = None
    url: Optional[str] = None
    reason: Optional[str] = None


class RadarEventScoreResult(BaseModel):
    """
    Agent 输出的规则二评分结构。

    注意：不含最终 S1–S4；调用方按分数阈值与准入规则定级。
    """

    exhibition_related: bool = Field(..., description="是否与展厅/长期展示空间明确相关")
    subject_confidence: str = Field(default="unknown", description="主体置信")
    space_object: Optional[str] = Field(default=None, description="展厅对象")
    action: Optional[str] = Field(default=None, description="需求/项目动作")
    place: Optional[str] = Field(default=None, description="地点")
    time_text: Optional[str] = Field(default=None, description="时间表述")
    evidence_score: Optional[int] = Field(
        default=None, description="证据强度分，合法档 85/75/60/45/25/10"
    )
    specificity_score: Optional[int] = Field(
        default=None, description="信息具体程度，合法档 15/10/5/0"
    )
    total_score: Optional[int] = Field(default=None, description="两维之和；不准入/失效为 null")
    tags: List[str] = Field(default_factory=list, description="事件标签（不计分）")
    expired_or_done: bool = Field(default=False, description="是否已失效/结束")
    fact_status: str = Field(default="unknown", description="事实状态")
    admission_hint: str = Field(
        default="pending_verify",
        description="准入提示：pass/reject_unrelated/pending_verify/expired",
    )
    score_reason: Optional[str] = Field(default=None, description="打分理由")
    evidences: List[RadarEventEvidenceItem] = Field(default_factory=list)
    discarded: List[RadarEventDiscardedItem] = Field(default_factory=list)
    search_count: int = Field(default=0, ge=0)
    extract_count: int = Field(default=0, ge=0)


class RadarEventCompany(BaseModel):
    """企业基础信息。"""

    company_id: Optional[Union[int, str]] = None
    company_name: str = Field(..., description="企业标准名")
    stock_code: Optional[str] = Field(default=None, description="证券代码")
    aliases: List[str] = Field(default_factory=list)
    industry: Optional[str] = None
    region: Optional[str] = None

    @field_validator("company_name")
    @classmethod
    def company_name_must_not_be_blank(cls, value: str) -> str:
        """校验公司名非空。"""
        stripped = value.strip() if isinstance(value, str) else ""
        if not stripped:
            raise ValueError("company_name 不能为空")
        return stripped

    @field_validator("aliases", mode="before")
    @classmethod
    def coerce_aliases(cls, value: Any) -> List[str]:
        """将 aliases 统一为字符串列表。"""
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("aliases 必须是数组")
        return [str(x).strip() for x in value if str(x).strip()]


class HuayuanRadarEventRequestContext(BaseModel):
    """请求中的 context 对象。"""

    company: RadarEventCompany = Field(..., description="企业基础信息")
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    query_hint: Optional[str] = None
    event_job_id: Optional[int] = None
    max_search_times: Optional[int] = Field(
        default=None,
        description="兼容旧字段：未传 max_bocha/max_anysearch 时，作为两工具各自上限",
    )
    max_bocha: Optional[int] = Field(default=None, description="博查搜索次数上限")
    max_anysearch: Optional[int] = Field(default=None, description="AnySearch 搜索次数上限")
    max_extract_times: Optional[int] = None
    max_results_per_search: Optional[int] = None


class HuayuanRadarEventRequest(BaseModel):
    """华院规则二评分请求。"""

    query: str = Field(..., description="评分任务提示")
    context: HuayuanRadarEventRequestContext = Field(..., description="公司基础信息上下文")
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


class HuayuanRadarEventResponse(BaseModel):
    """华院规则二评分响应。"""

    trace_id: str = Field(..., description="本次 Trace ID")
    radar_event_score: RadarEventScoreResult = Field(..., description="评分与证据")
    response: Optional[str] = Field(
        default=None, description="可选：结果 JSON 字符串，便于人工查看"
    )
