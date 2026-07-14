"""
Plan Executor 节点创建器
负责执行 plan 中的当前首步
"""
import logging
from typing import Callable

from langchain_core.messages import HumanMessage

from backend.domain.agents.factory import AgentFactory
from backend.domain.flows.models.definition import (
    AgentNodeConfig,
    FlowDefinition,
    ModelConfig,
    NodeDefinition,
    PlanExecutorNodeConfig,
)
from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.flows.nodes.planner_creator import _resolve_model_config
from backend.domain.planning.summarizer import summarize_tool_result
from backend.domain.planning.state_helpers import merge_edges_var
from backend.domain.state import FlowState, PastStepRecord
from backend.infrastructure.prompts.sys_prompt_builder import build_system_message

logger = logging.getLogger(__name__)


class PlanExecutorNodeCreator(NodeCreator):
    """Plan Executor 节点创建器"""

    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
        创建 Plan Executor 节点函数。

        Args:
            node_def: 节点定义
            flow_def: 流程定义

        Returns:
            Callable: 异步节点函数
        """
        config_dict = node_def.config
        model_config = _resolve_model_config(config_dict["model"], node_def.name)
        executor_config = PlanExecutorNodeConfig(
            prompt=config_dict["prompt"],
            model=model_config,
            tools=config_dict.get("tools"),
            execution_mode=config_dict.get("execution_mode", "agent_react"),
            result_max_chars=config_dict.get("result_max_chars", 2000),
        )

        agent_config = AgentNodeConfig(
            prompt=executor_config.prompt,
            model=executor_config.model,
            tools=executor_config.tools,
        )
        flow_dir = flow_def.flow_dir or ""
        node_name = node_def.name

        async def plan_executor_node_action(state: FlowState) -> FlowState:
            """Plan Executor 节点：执行 plan 首步"""
            # 运行时创建 Agent（图编译阶段不依赖 ProviderManager / 工具注册）
            agent_executor = AgentFactory.create_agent(
                config=agent_config,
                flow_dir=flow_dir,
            )

            plan = list(state.get("plan") or [])
            if not plan:
                logger.warning("[节点 %s] plan 为空，跳过执行", node_name)
                return {
                    "edges_var": merge_edges_var(state, {"has_plan": False}),
                }

            current_step = plan[0]
            step_id = current_step.get("step_id", "step_unknown")
            description = current_step.get("description", "")
            tool_hint = current_step.get("tool_name") or "由你根据步骤选择合适工具"

            logger.info("[节点 %s] 执行步骤: %s — %s", node_name, step_id, description)

            # 标记当前步骤为进行中
            current_step = {**current_step, "status": "in_progress"}
            plan[0] = current_step

            history_messages = list(state.get("history_messages") or [])
            current_message = state.get("current_message")
            msgs = history_messages.copy()
            if current_message:
                msgs.append(current_message)

            task_instruction = (
                f"【当前仅需完成以下单步任务，完成后简洁汇报结果】\n"
                f"步骤 ID: {step_id}\n"
                f"任务描述: {description}\n"
                f"建议工具: {tool_hint}\n"
                "禁止编造数据，必须基于工具真实返回结果作答。"
            )
            msgs.append(HumanMessage(content=task_instruction))

            sys_msg = build_system_message(
                prompt_cache_key=agent_executor.prompt_cache_key,
                state=state,
            )

            success = True
            error_msg = None
            output_text = ""

            try:
                if executor_config.execution_mode == "agent_react":
                    result = await agent_executor.ainvoke(
                        msgs=msgs,
                        callbacks=None,
                        sys_msg=sys_msg,
                    )
                    output_text = result.get("output", "") or ""
                else:
                    # tool_direct 首期仅占位，回退到 agent_react 行为
                    result = await agent_executor.ainvoke(
                        msgs=msgs,
                        callbacks=None,
                        sys_msg=sys_msg,
                    )
                    output_text = result.get("output", "") or ""
            except Exception as e:
                success = False
                error_msg = str(e)
                output_text = f"步骤执行失败: {error_msg}"
                logger.error(
                    "[节点 %s] 步骤 %s 执行失败: %s",
                    node_name,
                    step_id,
                    e,
                    exc_info=True,
                )

            result_summary = summarize_tool_result(
                output_text,
                max_chars=executor_config.result_max_chars,
            )

            past_record: PastStepRecord = {
                "step_id": step_id,
                "description": description,
                "result_summary": result_summary,
                "success": success,
                "error": error_msg,
            }

            # 移除已完成的首步
            remaining_plan = plan[1:] if len(plan) > 1 else []

            return {
                "plan": remaining_plan,
                "past_steps": [past_record],
                "edges_var": merge_edges_var(
                    state,
                    {"has_plan": len(remaining_plan) > 0},
                ),
            }

        return plan_executor_node_action
