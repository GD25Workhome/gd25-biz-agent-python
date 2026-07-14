"""
Planner 节点创建器
负责根据用户目标生成结构化执行计划
"""
import logging
from typing import Callable, List, Optional

from langchain_core.messages import HumanMessage

from backend.domain.flows.models.definition import (
    FlowDefinition,
    ModelConfig,
    NodeDefinition,
    PlanNodeConfig,
)
from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.planning.models import PlanOutput
from backend.domain.planning.state_helpers import (
    build_plan_context,
    get_objective,
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


def _resolve_model_config(model_dict: dict, node_name: str) -> ModelConfig:
    """解析并补全 ModelConfig（缺 name 时使用 provider 默认模型）。"""
    model_dict = model_dict.copy()
    if "name" not in model_dict or not model_dict["name"]:
        provider_name = model_dict.get("provider")
        if provider_name:
            from backend.infrastructure.llm.providers.manager import ProviderManager

            if not ProviderManager.is_loaded():
                ProviderManager.load_providers()
            provider_config = ProviderManager.get_provider(provider_name)
            if provider_config and provider_config.default_model:
                model_dict["name"] = provider_config.default_model
                logger.info(
                    "[节点 %s] 使用 provider '%s' 的默认模型: %s",
                    node_name,
                    provider_name,
                    provider_config.default_model,
                )
    return ModelConfig(**model_dict)


class PlannerNodeCreator(NodeCreator):
    """Planner 节点创建器"""

    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
        创建 Planner 节点函数。

        Args:
            node_def: 节点定义
            flow_def: 流程定义

        Returns:
            Callable: 异步节点函数
        """
        config_dict = node_def.config
        model_config = _resolve_model_config(config_dict["model"], node_def.name)
        plan_config = PlanNodeConfig(
            prompt=config_dict["prompt"],
            model=model_config,
            max_steps=config_dict.get("max_steps", 8),
            max_iterations=config_dict.get("max_iterations", 20),
        )
        allowed_tools: Optional[List[str]] = config_dict.get("tools")

        prompt_cache_key = prompt_manager.cached_prompt(
            prompt_path=plan_config.prompt,
            flow_dir=flow_def.flow_dir or "",
        )
        node_name = node_def.name

        async def planner_node_action(state: FlowState) -> FlowState:
            """Planner 节点：生成结构化执行计划"""
            objective = get_objective(state)
            if not objective:
                logger.warning("[节点 %s] 用户目标为空，无法规划", node_name)
                return {
                    "plan": [],
                    "plan_iteration": 0,
                    "plan_finished": True,
                    "edges_var": merge_edges_var(
                        state,
                        {"has_plan": False, "plan_finished": True, "should_abort": False},
                    ),
                }

            llm = get_llm(
                provider=plan_config.model.provider,
                model=plan_config.model.name,
                temperature=plan_config.model.temperature,
                thinking=plan_config.model.thinking,
                reasoning_effort=plan_config.model.reasoning_effort,
                timeout=plan_config.model.timeout,
            )

            sys_msg = build_system_message(prompt_cache_key=prompt_cache_key, state=state)
            context = build_plan_context(state)
            human_content = (
                f"请为以下用户目标制定执行计划（最多 {plan_config.max_steps} 步）。\n\n"
                f"{context}\n\n"
                "请输出结构化步骤列表。"
            )
            messages = [sys_msg, HumanMessage(content=human_content)]

            try:
                plan_output = await invoke_structured_llm(llm, PlanOutput, messages)
            except Exception as e:
                logger.error("[节点 %s] Planner 结构化输出失败: %s", node_name, e, exc_info=True)
                return {
                    "plan": [],
                    "plan_iteration": 0,
                    "plan_finished": True,
                    "plan_response": "抱歉，暂时无法为您的请求制定执行计划，请稍后重试。",
                    "flow_msgs": [],
                    "edges_var": merge_edges_var(
                        state,
                        {"has_plan": False, "plan_finished": True, "should_abort": False},
                    ),
                }

            steps = plan_output.steps[: plan_config.max_steps]
            steps = validate_tool_names(steps, allowed_tools)
            plan = plan_steps_to_typed_dicts(steps)
            has_plan = len(plan) > 0

            logger.info(
                "[节点 %s] 生成计划: step_count=%d, reasoning=%s",
                node_name,
                len(plan),
                (plan_output.reasoning or "")[:200],
            )

            return {
                "objective": objective,
                "plan": plan,
                "plan_iteration": 0,
                "plan_finished": False,
                "plan_metadata": {
                    "planner_model": plan_config.model.name,
                    "step_count": len(plan),
                    "reasoning": plan_output.reasoning,
                },
                "edges_var": merge_edges_var(
                    state,
                    {
                        "has_plan": has_plan,
                        "plan_finished": False,
                        "should_abort": False,
                    },
                ),
            }

        return planner_node_action
