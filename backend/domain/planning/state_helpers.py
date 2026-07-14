"""
Plan-and-Execute 状态辅助工具
"""
from typing import Any, Dict, List, Optional

from backend.domain.state import FlowState, PlanStep
from backend.domain.planning.models import PlanStepModel


def merge_edges_var(state: FlowState, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    合并 edges_var 更新，避免 Plan 节点覆盖已有路由变量。

    Args:
        state: 当前流程状态
        updates: 待合并的路由变量

    Returns:
        Dict[str, Any]: 合并后的 edges_var
    """
    edges_var = (state.get("edges_var") or {}).copy()
    edges_var.update(updates)
    return edges_var


def get_objective(state: FlowState) -> str:
    """
    从状态中提取用户目标。

    Args:
        state: 流程状态

    Returns:
        str: 用户目标文本
    """
    objective = state.get("objective")
    if objective and str(objective).strip():
        return str(objective).strip()

    current_message = state.get("current_message")
    if current_message is not None and hasattr(current_message, "content"):
        content = current_message.content
        if content:
            return str(content).strip()

    return ""


def build_plan_context(state: FlowState) -> str:
    """
    构建供 Planner / Replanner 使用的上下文摘要。

    Args:
        state: 流程状态

    Returns:
        str: 上下文文本
    """
    parts: List[str] = []
    objective = get_objective(state)
    if objective:
        parts.append(f"用户目标：{objective}")

    plan = state.get("plan") or []
    if plan:
        parts.append("当前剩余计划：")
        for idx, step in enumerate(plan, start=1):
            desc = step.get("description", "")
            tool = step.get("tool_name") or "未指定"
            parts.append(f"  {idx}. [{step.get('step_id', '')}] {desc} (工具: {tool})")

    past_steps = state.get("past_steps") or []
    if past_steps:
        parts.append("已执行步骤：")
        for record in past_steps:
            status = "成功" if record.get("success") else "失败"
            parts.append(
                f"  - [{record.get('step_id', '')}] {record.get('description', '')}: "
                f"{status} — {record.get('result_summary', '')[:500]}"
            )

    prompt_vars = state.get("prompt_vars") or {}
    if prompt_vars.get("user_info"):
        parts.append(f"用户信息：{prompt_vars.get('user_info')}")

    return "\n".join(parts)


def plan_steps_to_typed_dicts(steps: List[PlanStepModel]) -> List[PlanStep]:
    """
    将 Pydantic 计划步骤转为 FlowState 使用的 TypedDict 列表。

    Args:
        steps: Pydantic 计划步骤列表

    Returns:
        List[PlanStep]: TypedDict 格式计划
    """
    result: List[PlanStep] = []
    for step in steps:
        result.append(
            {
                "step_id": step.step_id,
                "description": step.description,
                "tool_name": step.tool_name,
                "expected_output": step.expected_output,
                "status": "pending",
            }
        )
    return result


def validate_tool_names(
    steps: List[PlanStepModel],
    allowed_tools: Optional[List[str]] = None,
) -> List[PlanStepModel]:
    """
    校验计划步骤中的工具名；未知工具名清空为 None 并保留步骤。

    Args:
        steps: 计划步骤
        allowed_tools: 允许的工具名列表；None 表示不校验

    Returns:
        List[PlanStepModel]: 校验后的步骤
    """
    if not allowed_tools:
        return steps

    allowed_set = set(allowed_tools)
    validated: List[PlanStepModel] = []
    for step in steps:
        if step.tool_name and step.tool_name not in allowed_set:
            validated.append(
                step.model_copy(update={"tool_name": None})
            )
        else:
            validated.append(step)
    return validated
