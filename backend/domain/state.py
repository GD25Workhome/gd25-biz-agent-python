"""
流程状态定义
定义流程执行过程中的状态数据结构
"""
import operator
from typing import TypedDict, List, Optional, Dict, Any, Annotated, Literal
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages


class PlanStep(TypedDict, total=False):
    """Plan-and-Execute 单步计划项"""

    step_id: str
    description: str
    tool_name: Optional[str]
    expected_output: Optional[str]
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"]


class PastStepRecord(TypedDict, total=False):
    """Plan-and-Execute 已执行步骤记录"""

    step_id: str
    description: str
    result_summary: str
    success: bool
    error: Optional[str]


class TeamTranscriptItem(TypedDict, total=False):
    """Team 单条发言摘要（供调试 / 限长落库）"""

    source: str
    content: str
    type: str


class TeamResult(TypedDict, total=False):
    """autogen_team 节点结构化结果"""

    team_mode: Literal["round_robin", "selector", "swarm"]
    stop_reason: Optional[str]
    message_count: int
    final_content: str
    approved: bool
    error: Optional[str]
    timed_out: bool
    hit_max_messages: bool


# ========== 对外 Input Schema ==========
# 图接收的输入：只包含调用方需要传入的字段
class FlowInputSchema(TypedDict, total=False):
    """图对外输入 schema"""
    current_message: HumanMessage
    history_messages: List[BaseMessage]
    session_id: str
    token_id: Optional[str]
    trace_id: Optional[str]
    prompt_vars: Optional[Dict[str, Any]]


# ========== 对外 Output Schema ==========
# 图返回的输出：只包含 API 需要的字段
class FlowOutputSchema(TypedDict, total=False):
    """图对外输出 schema"""
    flow_msgs: List[BaseMessage]  # Chat 路由主要使用
    session_id: str  # 便于链路追踪


# ========== 内部完整 State ==========
class FlowState(TypedDict, total=False):
    """
    流程状态数据结构（内部完整 schema）

    用于在流程执行过程中在节点间传递数据。
    图的 input_schema 和 output_schema 为其子集，用于约束对外输入输出。
    """
    current_message: HumanMessage  # 当前用户消息
    history_messages: List[BaseMessage]  # 历史消息列表
    flow_msgs: Annotated[List[BaseMessage], add_messages]  # 流程中间消息，使用 reducer 追加（不覆盖）
    session_id: str  # 会话ID
    token_id: Optional[str]  # 令牌ID（用于工具参数注入）
    trace_id: Optional[str]  # Trace ID（用于可观测性追踪）
    prompt_vars: Optional[Dict[str, Any]]  # 字典类型，用于存储提示词中的变量
    edges_var: Optional[Dict[str, Any]]  # 边条件判断变量存储（通用化设计）
    persistence_edges_var: Optional[Dict[str, Any]]  # 持久化边变量通道，透传到任意下级节点，边条件合并时 edges_var 优先

    # ========== Plan-and-Execute 扩展 ==========
    objective: str  # 用户目标（通常取自 current_message）
    plan: List[PlanStep]  # 当前待执行计划（Replanner 可整体替换）
    past_steps: Annotated[List[PastStepRecord], operator.add]  # 历史执行记录（追加型 reducer）
    plan_response: Optional[str]  # Replanner 判定完成时的最终回复
    plan_finished: bool  # 是否结束（供条件边路由）
    plan_iteration: int  # Executor-Replanner 循环次数（熔断用）
    plan_metadata: Optional[Dict[str, Any]]  # 规划元数据（模型、步骤数等）

    # ========== AutoGen Team 扩展 ==========
    team_result: Optional[TeamResult]  # autogen_team 结构化结果
    team_transcript: Optional[List[TeamTranscriptItem]]  # 限长 transcript（默认不写）

