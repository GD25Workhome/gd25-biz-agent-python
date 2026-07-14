"""
AutoGen Team 节点创建器

在 LangGraph 节点内运行 AgentChat RoundRobinGroupChat，结果写回 FlowState。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from langchain_core.messages import HumanMessage

from backend.domain.autogen.result_bridge import failure_flow_patch, to_flow_patch
from backend.domain.autogen.tool_bridge import wrap_registry_tools
from backend.domain.flows.models.autogen_config import (
    SUPPORTED_TEAM_MODES,
    AutogenTeamNodeConfig,
)
from backend.domain.flows.models.definition import FlowDefinition, ModelConfig, NodeDefinition
from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.state import FlowState
from backend.infrastructure.llm.autogen_client import get_autogen_model_client
from backend.infrastructure.prompts.manager import prompt_manager
from backend.infrastructure.prompts.sys_prompt_builder import build_system_message

logger = logging.getLogger(__name__)

_TIMEOUT_USER_MSG = "评审协作超时，请稍后重试或缩短任务描述。"
_ERROR_USER_MSG = "评审协作暂时不可用，请稍后重试。"


def _resolve_model_config(model_dict: dict, node_name: str) -> ModelConfig:
    """
        解析并补全 ModelConfig（缺 name 时使用 provider 默认模型）。

        Args:
            model_dict: YAML 中的 model 字典
            node_name: 节点名（用于日志）

        Returns:
            ModelConfig 实例
    """
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


def _build_task(state: FlowState, config: AutogenTeamNodeConfig) -> str:
    """
        从 FlowState 拼装 AutoGen task 文本。

        Args:
            state: 当前流程状态
            config: 节点配置

        Returns:
            task 字符串
    """
    current = state.get("current_message")
    if isinstance(current, HumanMessage):
        user_message = str(current.content or "")
    elif current is not None:
        user_message = str(getattr(current, "content", current) or "")
    else:
        user_message = str(state.get("objective") or "")

    task_cfg = config.task
    if task_cfg.template:
        task = task_cfg.template.format(user_message=user_message)
    else:
        task = user_message

    keys = task_cfg.include_prompt_vars_keys
    if keys:
        prompt_vars = state.get("prompt_vars") or {}
        extras: List[str] = []
        for key in keys:
            if key in prompt_vars:
                extras.append(f"{key}: {prompt_vars[key]}")
        if extras:
            task = task + "\n\n附加上下文:\n" + "\n".join(extras)
    return task


async def _run_autogen_team_node(
    state: FlowState,
    config: AutogenTeamNodeConfig,
    flow_dir: str,
    node_name: str,
) -> Dict[str, Any]:
    """
        执行 RoundRobin Team 并将结果转为 FlowState 补丁。

        Args:
            state: 当前状态
            config: 节点配置
            flow_dir: 流程目录
            node_name: 节点名称

        Returns:
            FlowState 补丁字典
    """
    team = None
    try:
        # 1. 构建模型客户端
        model_client = get_autogen_model_client(
            provider=config.model.provider,
            model=config.model.name,
            temperature=config.model.temperature,
        )

        # 2. 构建各 AssistantAgent
        participants: List[AssistantAgent] = []
        token_id = state.get("token_id")
        for spec in config.agents:
            # 先拿到缓存 key，再取正文（cached_prompt 返回的是路径 key，不是内容）
            prompt_cache_key = prompt_manager.cached_prompt(spec.system_prompt, flow_dir)
            # 与 agent 节点一致：按 state 替换占位符后得到真正系统提示词
            system_message = build_system_message(
                prompt_cache_key=prompt_cache_key,
                state=state,
            ).content
            tools = wrap_registry_tools(spec.tools, token_id=token_id)
            participants.append(
                AssistantAgent(
                    name=spec.name,
                    model_client=model_client,
                    system_message=system_message,
                    tools=tools or None,
                )
            )

        # 3. 终止条件与 Team
        termination = TextMentionTermination(config.termination.text_mention) | MaxMessageTermination(
            config.termination.max_messages
        )
        team = RoundRobinGroupChat(participants, termination_condition=termination)

        # 4. 拼装 task 并运行
        task = _build_task(state, config)
        logger.info(
            "[节点 %s] 启动 autogen_team mode=%s agents=%s timeout=%s",
            node_name,
            config.team_mode,
            [a.name for a in config.agents],
            config.timeout_seconds,
        )

        result = await asyncio.wait_for(team.run(task=task), timeout=config.timeout_seconds)
        # 成功：走结果桥
        return to_flow_patch(result, config, state)
    except asyncio.TimeoutError:
        logger.warning("[节点 %s] autogen_team 超时 timeout=%s", node_name, config.timeout_seconds)
        return failure_flow_patch(
            config,
            state,
            user_message=_TIMEOUT_USER_MSG,
            stop_reason="timeout",
            error=f"timeout after {config.timeout_seconds}s",
            timed_out=True,
        )
    except Exception as exc:  # noqa: BLE001 - 节点级降级
        logger.error("[节点 %s] autogen_team 异常: %s", node_name, exc, exc_info=True)
        return failure_flow_patch(
            config,
            state,
            user_message=_ERROR_USER_MSG,
            stop_reason="error",
            error=str(exc),
            timed_out=False,
        )
    finally:
        # 5. 重置 Team，避免同进程污染下一次任务
        if team is not None:
            try:
                await team.reset()
            except Exception as reset_exc:  # noqa: BLE001
                logger.warning("[节点 %s] team.reset 失败: %s", node_name, reset_exc)


class AutogenTeamNodeCreator(NodeCreator):
    """创建 type=autogen_team 的节点函数。"""

    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
            创建异步节点函数。

            Args:
                node_def: 节点定义
                flow_def: 流程定义

            Returns:
                async (FlowState) -> dict

            Raises:
                ValueError: team_mode 不受支持或配置非法
        """
        raw_config = dict(node_def.config or {})
        # 解析模型缺省 name
        if "model" in raw_config and isinstance(raw_config["model"], dict):
            model_config = _resolve_model_config(raw_config["model"], node_def.name)
            raw_config["model"] = model_config.model_dump()

        config = AutogenTeamNodeConfig.model_validate(raw_config)
        if config.team_mode not in SUPPORTED_TEAM_MODES:
            raise ValueError(
                f"autogen_team 首期仅支持 {sorted(SUPPORTED_TEAM_MODES)}，"
                f"当前: {config.team_mode}"
            )

        flow_dir = flow_def.flow_dir or ""
        node_name = node_def.name

        async def node_fn(state: FlowState) -> Dict[str, Any]:
            return await _run_autogen_team_node(
                state=state,
                config=config,
                flow_dir=flow_dir,
                node_name=node_name,
            )

        return node_fn
