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

# 产品 §3.4 合法离散分值（v3：固定 0 分档优先；60→55、10→5）
VALID_EVIDENCE_SCORES = {85, 75, 55, 45, 25, 5, 0}
VALID_SPECIFICITY_SCORES = {15, 10, 5, 0}
# 历史兼容：旧规则曾用 60/10，解析时容忍（放过、不产出），避免旧模型输出直接 500
LEGACY_EVIDENCE_SCORES = {60, 10}

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

# ---------------- 知识库（Milvus 检索 + 按需拉全文）默认值 ----------------
# 设计文档：exhibition projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md §3.3
#          / 03-子模块2-使用链路.md T2.2~T2.4
DEFAULT_KNOWLEDGE_MAX_DOCS = 20
DEFAULT_KNOWLEDGE_MAX_LOAD_TIMES = 3
# 单次 load_news_document 拉取正文的最大字符数（工具内固定，不接受请求覆盖）
DEFAULT_KNOWLEDGE_MAX_CHARS = 12000
# 知识库召回条目的来源层级（官网新闻权威性高于 P2 网络搜索）
SOURCE_LEVEL_KNOWLEDGE_BASE = "P0"
# 知识库证据在 briefs / evidences 中的工具名
TOOL_NAME_KNOWLEDGE_BASE = "knowledge_base"


class RadarEventKnowledgeConfig(BaseModel):
    """
    知识库使用开关（请求可选）。

    v3 目标架构：radar_event 评分链路**不再使用知识库**（默认 enabled=false）。
    显式传 enabled=true 时仍可开启（联调/回退用）；缺省一律关闭。
    """

    enabled: bool = Field(
        default=False,
        description="是否启用知识库（Milvus 检索 + 按需拉全文）；v3 缺省 false",
    )
    max_docs: Optional[int] = Field(
        default=None,
        description=f"本次并入 briefs 的知识库召回条数上限；缺省 {DEFAULT_KNOWLEDGE_MAX_DOCS}",
    )
    max_load_times: Optional[int] = Field(
        default=None,
        description=(
            "本次 load_news_document 最大拉取次数；"
            f"缺省 {DEFAULT_KNOWLEDGE_MAX_LOAD_TIMES}"
        ),
    )


class RadarEventEvidenceItem(BaseModel):
    """单条可追溯证据（evidences[] 为真相源）。"""

    evidence_no: Optional[int] = Field(default=None, description="事件内稳定序号，从 0 起")
    source_type: Optional[str] = Field(
        default=None, description="web | knowledge_base"
    )
    doc_id: Optional[Union[int, str]] = Field(default=None, description="知识库文档 id")
    title: Optional[str] = Field(default=None, description="标题")
    summary: Optional[str] = Field(default=None, description="摘要")
    quote: Optional[str] = Field(default=None, description="短摘录，建议≤200字")
    url: Optional[str] = Field(default=None, description="原文 URL")
    publish_date: Optional[str] = Field(default=None, description="发布日期（原文表述）")
    source_host: Optional[str] = Field(default=None, description="来源主机")
    authority_tier: Optional[str] = Field(default=None, description="启发式权威档")
    source_level: Optional[str] = Field(
        default=None,
        description="来源层级 P0/P1/P2（知识库召回=P0）；缺省 None 由调用方兜底",
    )
    content_grade: Optional[str] = Field(default=None, description="KB：full|stub")
    cite_reason: Optional[str] = Field(default=None, description="为何引此条")
    kept: bool = Field(default=True, description="是否纳入计分证据")


class RadarEventScoreItem(BaseModel):
    """展厅评分子项（引用 evidence_no，不嵌套 Citation）。"""

    code: str
    score: Optional[int] = None
    score_reason: Optional[str] = None
    evidence_nos: List[int] = Field(default_factory=list)


class RadarEventDiscardedItem(BaseModel):
    """被排除的命中结果。"""

    title: Optional[str] = None
    url: Optional[str] = None
    reason: Optional[str] = None


class RadarEventScoreResult(BaseModel):
    """
    Agent 输出的规则二评分结构（v3）。

    主契约：两维离散分 + 证据链 + 准入（Java/下游兼容）。
    v3 扩展：建议等级、目标范围、采购范围、事件/展厅阶段、核验优先级、三时间等。
    """

    exhibition_related: bool = Field(..., description="是否与展厅/长期展示空间明确相关")
    subject_confidence: str = Field(default="unknown", description="主体置信")
    space_object: Optional[str] = Field(default=None, description="展厅对象")
    action: Optional[str] = Field(default=None, description="需求/项目动作")
    place: Optional[str] = Field(default=None, description="地点")
    place_region_id: Optional[int] = Field(
        default=None,
        description=(
            "展厅所在区域 region.id（Agent 用 region_lookup/region_children 查字典得到；"
            "落库用于 region_* 列，source=AI_PARSED；查不到为 null）"
        ),
    )
    time_text: Optional[str] = Field(default=None, description="工期/计划等自由时间表述（非列表主时间）")
    signal_summary: Optional[str] = Field(
        default=None,
        description="一句话展厅信号简述（列表主文案；有分时必填，禁止仅写 S1-S4）",
    )
    signal_time: Optional[str] = Field(
        default=None,
        description="需求在公开资料中出现的时间 YYYY-MM-DD 或 YYYY-MM；来自证据发布日，禁止用跑批日",
    )
    signal_time_evidence_no: Optional[int] = Field(
        default=None,
        description="signal_time 对应 evidences[].evidence_no",
    )
    fact_time_earliest: Optional[str] = Field(
        default=None,
        description=(
            "该簇**最早影响评分的事实时间**（立项/招标/签约），YYYY-MM-DD 或 YYYY-MM；"
            "时效闸门的计时基准（D8）——注意不是最新材料的发布日期"
        ),
    )
    fact_time_earliest_evidence_no: Optional[int] = Field(
        default=None,
        description="fact_time_earliest 对应 evidences[].evidence_no",
    )
    evidence_score: Optional[int] = Field(
        default=None, description="证据强度分，合法档 85/75/55/45/25/5/0（v3）"
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
    score_reason: Optional[str] = Field(default=None, description="总评理由")
    score_items: List[RadarEventScoreItem] = Field(default_factory=list)
    evidences: List[RadarEventEvidenceItem] = Field(default_factory=list)
    discarded: List[RadarEventDiscardedItem] = Field(default_factory=list)
    search_count: int = Field(default=0, ge=0)
    extract_count: int = Field(default=0, ge=0)
    web_hit_count: int = Field(default=0, ge=0)
    kb_hit_count: int = Field(default=0, ge=0)

    # ---------------- v3 扩展字段（供 S3 排序 / 展品中心展示 / 事件更新） ----------------
    target_scope: Optional[str] = Field(
        default=None, description="enterprise | gov_or_park | excluded"
    )
    suggested_level: Optional[str] = Field(
        default=None, description="Agent 建议等级 S1-S4（最终由系统区间自检确认）"
    )
    suggested_level_reason: Optional[str] = Field(
        default=None, description="建议等级依据"
    )
    procurement_scope: Optional[str] = Field(
        default=None,
        description="采购范围：exhibition_tender|front_building_only|mixed|intent_phase|unknown",
    )
    event_stage: Optional[str] = Field(
        default=None,
        description="空间事件阶段：planned|in_preparation|under_construction|moved_in|launch_done|park_open|unknown",
    )
    exhibition_stage: Optional[str] = Field(
        default=None,
        description="展厅阶段：none_known|planned|tendering|implementing|completed|unknown",
    )
    is_potential: bool = Field(default=False, description="潜在关联是否为推断")
    signal_category: Optional[str] = Field(
        default=None, description="命中的潜在信号目录类别（S3 潜在档）"
    )
    verify_priority_default: Optional[str] = Field(
        default=None, description="目录默认核验优先级 P0-P3"
    )
    verify_priority_adjusted: Optional[str] = Field(
        default=None, description="按阶段修正后的当前核验优先级 P0-P3"
    )
    verify_priority_reason: Optional[str] = Field(
        default=None, description="优先级修正原因"
    )
    planned_time: Optional[str] = Field(default=None, description="计划确认时间")
    expected_time: Optional[str] = Field(default=None, description="预计时间")
    actual_time: Optional[str] = Field(default=None, description="实际发生时间")
    date_precision: Optional[str] = Field(
        default=None, description="day|month|year|unknown"
    )
    rule_version: Optional[str] = Field(
        default=None, description='规则版本，如 "v3-2026-10-14"'
    )

    # ---------------- v3 多事件 / 关联字段（261019） ----------------
    event_ref: Optional[str] = Field(
        default=None, description="本次运行内的局部键（e0/e1…），供 score_items/evidences 引用"
    )
    event_name: Optional[str] = Field(
        default=None, description="规范展厅商机名（业务键核心，如「北京办公楼企业展厅」）"
    )
    event_relation: Optional[str] = Field(
        default=None,
        description="与既有事件的关系（由 Agent 判）：new|continue|close|ignored",
    )
    matched_event_id: Optional[int] = Field(
        default=None,
        description="continue/close 时指向输入 history 里的既有事件 id（代码会校验属本企业）",
    )
    parent_event_id: Optional[int] = Field(
        default=None, description="父事件 id（同一商机的根）；无则 null"
    )

    @field_validator("matched_event_id", "parent_event_id", mode="before")
    @classmethod
    def coerce_relation_ids(cls, value: Any) -> Optional[int]:
        """关联 id 容错：数字串/整数照收，其余（空串、非数字）归 None，避免整单校验失败。"""
        if value is None or value == "":
            return None
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    @field_validator("place_region_id", mode="before")
    @classmethod
    def coerce_region_id(cls, value: Any) -> Optional[int]:
        """区域 id 容错：数字串/整数照收，其余（含空串、非数字）归 None，避免整单校验失败。"""
        if value is None or value == "":
            return None
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None


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
    history_events_json: Optional[str] = Field(
        default=None,
        description="该公司既有事件摘要 JSON（M2 组装注入；缺省 []，供判断同一事件新阶段/独立新需求）",
    )
    max_search_times: Optional[int] = Field(
        default=None,
        description="兼容旧字段：未传 max_bocha/max_anysearch 时，作为两工具各自上限",
    )
    max_bocha: Optional[int] = Field(default=None, description="博查搜索次数上限")
    max_anysearch: Optional[int] = Field(default=None, description="AnySearch 搜索次数上限")
    max_extract_times: Optional[int] = None
    max_results_per_search: Optional[int] = None
    knowledge: Optional[RadarEventKnowledgeConfig] = Field(
        default=None,
        description="知识库使用开关（可选）；不传=默认启用 KB",
    )


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
    radar_event_score: RadarEventScoreResult = Field(..., description="评分与证据（第一个事件；兼容）")
    radar_event_scores: List[RadarEventScoreResult] = Field(
        default_factory=list,
        description="多事件结果（261019）；`radar_event_score` 为其第一个，向后兼容",
    )
    response: Optional[str] = Field(
        default=None, description="可选：结果 JSON 字符串，便于人工查看"
    )
    revision: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "复核留痕（裁定 D12）：`rule_gate` 的 before/after/判定 与 `auditor` 的 audit 说明；"
            "由 execute 落库到 `radar_event_job.revision_json`"
        ),
    )
