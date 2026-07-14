"""
Plan-and-Execute 结构化输出 Pydantic 模型
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PlanStepModel(BaseModel):
    """单步计划项（LLM 结构化输出）"""

    step_id: str = Field(description="步骤 ID，如 step_1")
    description: str = Field(description="步骤自然语言描述")
    tool_name: Optional[str] = Field(default=None, description="建议调用的工具名，可为空")
    expected_output: Optional[str] = Field(default=None, description="预期产出描述")


class PlanOutput(BaseModel):
    """Planner 节点结构化输出"""

    steps: List[PlanStepModel] = Field(description="有序执行步骤，保持细粒度")
    reasoning: Optional[str] = Field(default=None, description="规划理由，便于 Langfuse 审计")


class ReplannerOutput(BaseModel):
    """
    Replanner 节点结构化输出

    使用单一模型 + action 字段，避免 Union 结构化输出在部分模型上的兼容问题。
    """

    action: Literal["continue", "finish"] = Field(description="continue=继续执行，finish=任务完成")
    steps: List[PlanStepModel] = Field(
        default_factory=list,
        description="action=continue 时的修订后剩余步骤",
    )
    response: Optional[str] = Field(
        default=None,
        description="action=finish 时面向用户的最终回复",
    )
    reasoning: Optional[str] = Field(default=None, description="重规划理由")
