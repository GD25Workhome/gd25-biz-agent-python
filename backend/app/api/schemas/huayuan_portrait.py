"""
华院五维画像评分 Schema（对接 exhibition /huayuan/portrait）
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


PortraitTier = Literal["strong", "stronger", "medium", "weak_or_unknown"]
FactStatus = Literal["confirmed", "inferred", "unknown", "conflict"]
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


class PortraitEvidence(BaseModel):
    """单条证据引用。"""

    ref_id: Optional[Union[int, str]] = Field(default=None, description="证据文档 id")
    quote: Optional[str] = Field(default=None, description="短摘录/要点，建议≤200字")


class PortraitDimension(BaseModel):
    """单个画像维度的候选档位。"""

    code: str = Field(..., description="维度编码")
    tier: str = Field(..., description="档位枚举")
    fact_status: str = Field(default="unknown", description="证据状态")
    evidence: List[PortraitEvidence] = Field(default_factory=list)
    missing_reason: Optional[str] = Field(default=None, description="信息不足原因")


class PortraitResult(BaseModel):
    """Agent 输出的画像结构（不含分数）。"""

    dimensions: List[PortraitDimension] = Field(default_factory=list)
    loaded_file_ids: List[str] = Field(default_factory=list)
    discarded_file_ids: List[str] = Field(default_factory=list)
    load_count: int = Field(default=0, ge=0)


class HuayuanPortraitRequestContext(BaseModel):
    """请求中的 context 对象（字段宽松以兼容业务侧演进）。"""

    profile_job_id: Optional[int] = None
    rule_version: Optional[str] = None
    company: Optional[Dict[str, Any]] = None
    rule_prefill: Optional[Dict[str, Any]] = None
    file_ids: List[str] = Field(default_factory=list)
    file_metas: List[Dict[str, Any]] = Field(default_factory=list)
    stats: Optional[Dict[str, Any]] = None
    max_load_times: Optional[int] = Field(default=None, description="建议最大加载次数")
    document_tool_base_url: Optional[str] = Field(
        default=None, description="exhibition 工具 API 基址"
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
