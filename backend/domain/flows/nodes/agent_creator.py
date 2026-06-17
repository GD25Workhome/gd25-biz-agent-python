"""
Agent 节点创建器

将 flow.yaml 中 type=agent 的节点定义编译为 LangGraph 异步节点函数：
组装提示词与消息 → 调用 ReAct Agent → 解析 LLM JSON 输出写入 edges_var / flow_msgs。
"""
import logging
import json
from typing import Any, Callable, Dict, List, Optional

from typing_extensions import override

from langchain_core.messages import AIMessage

from backend.domain.state import FlowState
from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition, AgentNodeConfig, ModelConfig
from backend.domain.agents.factory import AgentFactory
from backend.infrastructure.prompts.sys_prompt_builder import build_system_message

logger = logging.getLogger(__name__)


class AgentNodeCreator(NodeCreator):
    """
        将 flow.yaml 的 agent 节点编译为闭包形式的异步节点函数。

        编译期创建 AgentExecutor（含 LLM、工具、提示词缓存）；运行期每轮执行 agent_node_action。
    """

    @override
    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
            实现 NodeCreator.create：解析 agent 节点配置并返回 LangGraph 节点函数。

            Args:
                node_def: flow.yaml 中的 agent 节点（name、config.prompt/model/tools）
                flow_def: 所属流程（flow_dir 用于解析提示词相对路径）

            Returns:
                Callable: 异步节点函数 agent_node_action(state) -> state
        """
        config_dict = node_def.config
        model_dict = config_dict["model"].copy()

        # 1. model.name 缺失时从 ProviderManager 取该 provider 的 default_model
        if "name" not in model_dict or not model_dict["name"]:
            provider_name = model_dict.get("provider")
            if provider_name:
                from backend.infrastructure.llm.providers.manager import ProviderManager

                if not ProviderManager.is_loaded():
                    # ProviderManager.load_providers：加载 config/model_providers.yaml
                    ProviderManager.load_providers()

                provider_config = ProviderManager.get_provider(provider_name)
                if provider_config and provider_config.default_model:
                    model_dict["name"] = provider_config.default_model
                    logger.info(
                        f"[节点 {node_def.name}] 使用 provider '{provider_name}' 的默认模型: "
                        f"{provider_config.default_model}"
                    )

        # 2. 校验并组装 AgentNodeConfig
        model_config = ModelConfig(**model_dict)
        agent_config = AgentNodeConfig(
            prompt=config_dict["prompt"],
            model=model_config,
            tools=config_dict.get("tools"),
        )

        # 3. 编译期创建 AgentExecutor（内层 ReAct 图 + 工具 + 提示词缓存键）
        agent_executor = AgentFactory.create_agent(
            config=agent_config,
            flow_dir=flow_def.flow_dir or "",
        )

        node_name = node_def.name

        async def agent_node_action(state: FlowState) -> FlowState:
            """
                单次 Agent 节点执行：替换占位符 → 调 LLM → 解析 JSON → 更新 state。

                edges_var 每轮重置为空 dict，避免污染下游条件边；可选 key 同步到 persistence_edges_var。
            """
            # 1. 用 prompt_vars / edges_prompt_vars 替换系统提示词占位符
            # build_system_message：从 state 取变量并封装 SystemMessage
            sys_msg = build_system_message(
                prompt_cache_key=agent_executor.prompt_cache_key,
                state=state,
            )

            # 2. 拼装 history_messages + current_message 作为 LLM 对话输入
            history_messages = state.get("history_messages", [])
            current_message = state.get("current_message")
            msgs = history_messages.copy()
            if current_message:
                msgs.append(current_message)

            if not msgs:
                logger.warning(f"[节点 {node_name}] 消息列表为空，跳过执行")
                return state

            # 3. 调用内层 ReAct Agent（LLM + 可选工具循环）
            result = await agent_executor.ainvoke(
                msgs=msgs,
                callbacks=None,
                sys_msg=sys_msg,
            )

            # 4. 浅拷贝 state 并重置 edges_var，防止上游边变量影响本节点下游路由
            new_state = state.copy()
            new_state["edges_var"] = {}

            if "output" in result:
                output = result["output"]
                output_data = result.get("output_data")

                # 5. 将结构化字段写入 edges_var（dict 直写或字符串 JSON 解析）
                try:
                    if isinstance(output_data, dict):
                        _apply_output_data_to_edges_var(output_data, new_state["edges_var"])
                        logger.debug(
                            f"[节点 {node_name}] 从 output_data(dict) 提取数据到 edges_var: "
                            f"{list(new_state['edges_var'].keys())}"
                        )
                    elif isinstance(output, str) and output.strip():
                        # _parse_json_from_output_string：容错解析 LLM 输出的 JSON 根对象
                        parsed = _parse_json_from_output_string(output)
                        if isinstance(parsed, dict):
                            _apply_output_data_to_edges_var(parsed, new_state["edges_var"])
                            logger.debug(
                                f"[节点 {node_name}] 从输出字符串解析到 edges_var: "
                                f"{list(new_state['edges_var'].keys())}"
                            )
                        else:
                            logger.warning(
                                f"[节点 {node_name}] 输出字符串无法解析为 JSON，长度=%d",
                                len(output),
                            )
                except Exception as e:
                    logger.warning(
                        f"[节点 {node_name}] 解析输出 JSON 失败: {e}",
                        exc_info=True,
                    )

                # 6. 按配置将指定 key 同步到 persistence_edges_var（跨节点条件边可读）
                persist_keys = config_dict.get("persist_to_persistence_edges_var")
                if isinstance(persist_keys, list) and len(persist_keys) > 0:
                    # 必须 copy：浅拷贝下直接改嵌套 dict 会污染入参 state
                    new_state["persistence_edges_var"] = (state.get("persistence_edges_var") or {}).copy()
                    for k in persist_keys:
                        if k in new_state["edges_var"]:
                            new_state["persistence_edges_var"][k] = new_state["edges_var"][k]
                    logger.debug(
                        f"[节点 {node_name}] 将 edges_var 的 key 同步到 persistence_edges_var: {persist_keys}"
                    )

                # 7. AI 回复追加到 flow_msgs（history_messages 不写入中间节点输出）
                ai_message = AIMessage(content=output)
                new_state["flow_msgs"] = [ai_message]

            return new_state

        return agent_node_action


# ---------------------------------------------------------------------------
# 模块内辅助函数：LLM 输出 JSON 解析与 edges_var 写入（供 agent_node_action 调用）
# ---------------------------------------------------------------------------

# 写入 edges_var 时跳过的 key（回复正文与推理摘要不参与条件边变量）
_EDGES_VAR_SKIP_KEYS = frozenset(["response_content", "reasoning_summary", "additional_fields"])


def _apply_output_data_to_edges_var(output_data: Dict[str, Any], edges_var: Dict[str, Any]) -> None:
    """
        将 Agent 结构化输出合并进 edges_var，供下游条件边与提示词占位符使用。

        跳过 response_content、reasoning_summary；additional_fields 内层键展平写入 edges_var。

        Args:
            output_data: LLM 返回并已解析的字典
            edges_var: 当前节点产出的边变量字典（就地修改）
    """
    if not isinstance(output_data, dict):
        return
    for key, value in output_data.items():
        if key not in _EDGES_VAR_SKIP_KEYS:
            edges_var[key] = value
    if "additional_fields" in output_data and isinstance(output_data["additional_fields"], dict):
        for key, value in output_data["additional_fields"].items():
            edges_var[key] = value


def _parse_json_from_output_string(output: str) -> Optional[Dict[str, Any]]:
    """
        从 LLM 输出字符串中尽可能提取根 JSON 对象。

        依次尝试：整段解析 → 双层编码再解析 → 括号匹配截取根对象（必要时先修复换行）。

        Args:
            output: Agent 返回的 output 字符串

        Returns:
            解析成功的 dict；无法解析时返回 None
    """
    if not output or not isinstance(output, str):
        return None
    s = output.strip()

    # 1. 整段 json.loads
    try:
        parsed = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        return parsed

    # 2. 双层编码：外层解析结果为 str 时再解析内层
    if isinstance(parsed, str):
        inner = parsed.strip()
        if inner.startswith("{"):
            try:
                again = json.loads(inner)
                if isinstance(again, dict):
                    return again
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                # _fix_unescaped_newlines_in_json_string：修复内层 JSON 字符串内未转义换行
                fixed_inner = _fix_unescaped_newlines_in_json_string(inner)
                again = json.loads(fixed_inner)
                if isinstance(again, dict):
                    return again
            except (json.JSONDecodeError, TypeError):
                pass

    # 3. 从首个 '{' 起括号匹配截取根对象
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    quote = None
    for i in range(start, len(s)):
        c = s[i]
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if not in_string:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    substring = s[start : i + 1]
                    try:
                        return json.loads(substring)
                    except (json.JSONDecodeError, TypeError):
                        pass
                    try:
                        fixed = _fix_unescaped_newlines_in_json_string(substring)
                        return json.loads(fixed)
                    except (json.JSONDecodeError, TypeError):
                        return None
            elif c in ('"', "'"):
                in_string = True
                quote = c
        else:
            if c == quote:
                in_string = False
    return None


def _fix_unescaped_newlines_in_json_string(raw: str) -> str:
    """
        修复 JSON 字符串值内未转义的换行，使 json.loads 可解析。

        仅处理双引号字符串内部字面 \\n/\\r，不改变 JSON 结构层面的换行。

        Args:
            raw: 原始 JSON 文本

        Returns:
            修复后的 JSON 文本
    """
    result: List[str] = []
    in_string = False
    escape = False
    quote_char = '"'
    i = 0
    while i < len(raw):
        c = raw[i]
        if escape:
            result.append(c)
            escape = False
            i += 1
            continue
        if c == "\\" and in_string:
            result.append(c)
            escape = True
            i += 1
            continue
        if c == quote_char:
            in_string = not in_string
            result.append(c)
            i += 1
            continue
        if in_string and c == "\n":
            result.append("\\n")
            i += 1
            continue
        if in_string and c == "\r":
            result.append("\\r")
            i += 1
            continue
        result.append(c)
        i += 1
    return "".join(result)
