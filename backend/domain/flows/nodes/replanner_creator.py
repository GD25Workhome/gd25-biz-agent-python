"""
Replanner 节点创建器
负责评估执行结果并决定继续执行或完成任务
"""
import logging
from typing import Callable, Optional

from langchain_core.messages import AIMessage, HumanMessage

from backend.domain.flows.models.definition import (
    FlowDefinition,
    NodeDefinition,
    PlanNodeConfig,
)
from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.flows.nodes.planner_creator import _resolve_model_config
from backend.domain.planning.models import ReplannerOutput
from backend.domain.planning.state_helpers import (
    build_plan_context,
    merge_edges_var,
    plan_steps_to_typed_dicts,
    validate_tool_names,
)
from backend.domain.planning.structured_output import invoke_structured_llm
from backend.domain.state import FlowState
from backend.infrastructure.llm.client import get_llm
from backend.infrastructure.prompts.manager import prompt_manager
from backend.infrastructure.prompts.sys_prompt_builder import build_system_message

logger = logging.getLogger(__name__)


class ReplannerNodeCreator(NodeCreator):
    """Replanner 节点创建器"""

    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
        创建 Replanner 节点函数。

        Args:
            node_def: 节点定义
            flow_def: 流程定义

        Returns:
            Callable: 异步节点函数
        """
        config_dict = node_def.config
        model_config = _resolve_model_config(config_dict["model"], node_def.name)
        replanner_config = PlanNodeConfig(
            prompt=config_dict["prompt"],
            model=model_config,
            max_steps=config_dict.get("max_steps", 8),
            max_iterations=config_dict.get("max_iterations", 20),
        )
        allowed_tools: Optional[List[str]] = config_dict.get("tools")

        prompt_cache_key = prompt_manager.cached_prompt(
            prompt_path=replanner_config.prompt,
            flow_dir=flow_def.flow_dir or "",
        )
        node_name = node_def.name

        async def replanner_node_action(state: FlowState) -> FlowState:
            """Replanner 节点：评估进度并决定继续或结束"""
            iteration = (state.get("plan_iteration") or 0) + 1
            max_iterations = replanner_config.max_iterations

            # 熔断：超过最大循环次数
            if iteration >= max_iterations:
                logger.warning(
                    "[节点 %s] 达到最大循环次数 %d，强制结束",
                    node_name,
                    max_iterations,
                )
                abort_msg = (
                    "抱歉，任务执行步骤较多，已达到系统处理上限。"
                    "请尝试将问题拆分为更小的子问题分别咨询。"
                )
                return {
                    "plan_iteration": iteration,
                    "plan_finished": True,
                    "plan_response": abort_msg,
                    "flow_msgs": [AIMessage(content=abort_msg)],
                    "edges_var": merge_edges_var(
                        state,
                        {
                            "plan_finished": True,
                            "should_abort": True,
                            "has_plan": False,
                        },
                    ),
                }

            remaining_plan = state.get("plan") or []
            past_steps = state.get("past_steps") or []

            # 无剩余步骤且无历史：直接结束
            if not remaining_plan and not past_steps:
                finish_msg = "抱歉，未能完成您的请求，请重新描述您的问题。"
                return {
                    "plan_iteration": iteration,
                    "plan_finished": True,
                    "plan_response": finish_msg,
                    "flow_msgs": [AIMessage(content=finish_msg)],
                    "edges_var": merge_edges_var(
                        state,
                        {
                            "plan_finished": True,
                            "should_abort": False,
                            "has_plan": False,
                        },
                    ),
                }

            llm = get_llm(
                provider=replanner_config.model.provider,
                model=replanner_config.model.name,
                temperature=replanner_config.model.temperature,
                thinking=replanner_config.model.thinking,
                reasoning_effort=replanner_config.model.reasoning_effort,
                timeout=replanner_config.model.timeout,
            )

            sys_msg = build_system_message(prompt_cache_key=prompt_cache_key, state=state)
            context = build_plan_context(state)
            human_content = (
                f"请根据以下执行进度，决定是继续执行（action=continue）还是完成任务（action=finish）。\n\n"
                f"{context}\n\n"
                f"当前循环次数: {iteration}/{max_iterations}"
            )
            messages = [sys_msg, HumanMessage(content=human_content)]

            try:
                replanner_output = await invoke_structured_llm(
                    llm, ReplannerOutput, messages
                )
            except Exception as e:
                logger.error(
                    "[节点 %s] Replanner 结构化输出失败: %s",
                    node_name,
                    e,
                    exc_info=True,
                )
                # 失败时：若还有剩余步骤则继续，否则结束
                if remaining_plan:
                    return {
                        "plan_iteration": iteration,
                        "plan_finished": False,
                        "edges_var": merge_edges_var(
                            state,
                            {
                                "plan_finished": False,
                                "should_abort": False,
                                "has_plan": True,
                            },
                        ),
                    }
                fallback_msg = "任务已部分完成，但无法生成最终总结，请查看上文结果。"
                return {
                    "plan_iteration": iteration,
                    "plan_finished": True,
                    "plan_response": fallback_msg,
                    "flow_msgs": [AIMessage(content=fallback_msg)],
                    "edges_var": merge_edges_var(
                        state,
                        {
                            "plan_finished": True,
                            "should_abort": False,
                            "has_plan": False,
                        },
                    ),
                }

            logger.info(
                "[节点 %s] Replanner 决策: action=%s, iteration=%d",
                node_name,
                replanner_output.action,
                iteration,
            )

            if replanner_output.action == "finish":
                response_text = (
                    replanner_output.response
                    or "任务已完成。"
                )
                return {
                    "plan_iteration": iteration,
                    "plan_finished": True,
                    "plan_response": response_text,
                    "plan": [],
                    "flow_msgs": [AIMessage(content=response_text)],
                    "edges_var": merge_edges_var(
                        state,
                        {
                            "plan_finished": True,
                            "should_abort": False,
                            "has_plan": False,
                        },
                    ),
                }

            # continue：用新步骤替换 plan
            steps = replanner_output.steps[: replanner_config.max_steps]
            steps = validate_tool_names(steps, allowed_tools)
            new_plan = plan_steps_to_typed_dicts(steps)

            # 若 continue 但未给出步骤，且原 plan 已空，则强制 finish
            if not new_plan and not remaining_plan:
                response_text = replanner_output.response or "任务已完成。"
                return {
                    "plan_iteration": iteration,
                    "plan_finished": True,
                    "plan_response": response_text,
                    "flow_msgs": [AIMessage(content=response_text)],
                    "edges_var": merge_edges_var(
                        state,
                        {
                            "plan_finished": True,
                            "should_abort": False,
                            "has_plan": False,
                        },
                    ),
                }

            # 若 continue 未给新步骤但原 plan 仍有剩余，保留原 plan
            final_plan = new_plan if new_plan else list(remaining_plan)

            return {
                "plan_iteration": iteration,
                "plan_finished": False,
                "plan": final_plan,
                "edges_var": merge_edges_var(
                    state,
                    {
                        "plan_finished": False,
                        "should_abort": False,
                        "has_plan": len(final_plan) > 0,
                    },
                ),
            }

        return replanner_node_action
