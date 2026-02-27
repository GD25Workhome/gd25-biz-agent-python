"""
Agent节点创建器
"""
import logging
import json
from typing import Any, Callable, Dict, List, Optional

from langchain_core.messages import AIMessage

from backend.domain.state import FlowState
from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition, AgentNodeConfig, ModelConfig
from backend.domain.agents.factory import AgentFactory
from backend.infrastructure.prompts.sys_prompt_builder import build_system_message

logger = logging.getLogger(__name__)

# 写入 edges_var 时跳过的 key（非业务边条件字段）
_EDGES_VAR_SKIP_KEYS = frozenset(["response_content", "reasoning_summary", "additional_fields"])


def _apply_output_data_to_edges_var(output_data: Dict[str, Any], edges_var: Dict[str, Any]) -> None:
    """
    将 Agent 解析后的 output_data 写入 edges_var。
    跳过 response_content、reasoning_summary、additional_fields；additional_fields 内容合并进 edges_var。
    """
    if not isinstance(output_data, dict):
        return
    for key, value in output_data.items():
        if key not in _EDGES_VAR_SKIP_KEYS:
            edges_var[key] = value
    if "additional_fields" in output_data and isinstance(output_data["additional_fields"], dict):
        for key, value in output_data["additional_fields"].items():
            edges_var[key] = value


def _fix_unescaped_newlines_in_json_string(raw: str) -> str:
    """
    将 JSON 字符串值内的未转义换行（\\n、\\r）替换为转义形式（两字符 \\ + n/r），
    使整段可被 json.loads 解析。仅处理双引号字符串内部，不改变结构换行。
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


def _parse_json_from_output_string(output: str) -> Optional[Dict[str, Any]]:
    """
    从输出字符串中解析 JSON 对象。
    1. 整段 json.loads；若得到 dict 则返回；
    2. 若得到 str（双层编码），再对该 str 解析一次；
    3. 失败则从第一个 '{' 起按括号匹配截取根对象；若截取后仍含未转义换行则先修复再解析。
    """
    if not output or not isinstance(output, str):
        return None
    s = output.strip()
    # 1. 整段解析
    try:
        parsed = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    # 2. 一次解析得到 str（双层编码）：再解析一次
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
                fixed_inner = _fix_unescaped_newlines_in_json_string(inner)
                again = json.loads(fixed_inner)
                if isinstance(again, dict):
                    return again
            except (json.JSONDecodeError, TypeError):
                pass
    # 3. 从第一个 '{' 起括号匹配截取
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


class AgentNodeCreator(NodeCreator):
    """Agent节点创建器"""
    
    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
        创建Agent节点函数
        
        Args:
            node_def: 节点定义
            flow_def: 流程定义
            
        Returns:
            Callable: Agent节点函数
        """
        # 解析节点配置
        config_dict = node_def.config
        model_dict = config_dict["model"].copy()
        
        # 如果缺少 name 字段，尝试从 provider 配置中获取默认值
        if "name" not in model_dict or not model_dict["name"]:
            provider_name = model_dict.get("provider")
            if provider_name:
                from backend.infrastructure.llm.providers.manager import ProviderManager
                
                # 确保 ProviderManager 已加载
                if not ProviderManager.is_loaded():
                    ProviderManager.load_providers()
                
                provider_config = ProviderManager.get_provider(provider_name)
                if provider_config and provider_config.default_model:
                    model_dict["name"] = provider_config.default_model
                    logger.info(
                        f"[节点 {node_def.name}] 使用 provider '{provider_name}' 的默认模型: "
                        f"{provider_config.default_model}"
                    )
        
        # 创建 ModelConfig（如果仍然缺少 name，会抛出 ValidationError）
        model_config = ModelConfig(**model_dict)
        agent_config = AgentNodeConfig(
            prompt=config_dict["prompt"],
            model=model_config,
            tools=config_dict.get("tools")
        )
        
        # 创建Agent
        agent_executor = AgentFactory.create_agent(
            config=agent_config,
            flow_dir=flow_def.flow_dir or ""
        )
        
        # 创建节点函数
        node_name = node_def.name
        
        async def agent_node_action(state: FlowState) -> FlowState:
            """Agent节点函数"""
            # 构建系统消息（自动替换占位符，内部从 state 中提取 prompt_vars）
            sys_msg = build_system_message(
                prompt_cache_key=agent_executor.prompt_cache_key,
                state=state
            )
            
            # 拼装消息列表：history_messages + current_message
            history_messages = state.get("history_messages", [])
            current_message = state.get("current_message")
            
            # 构建消息列表
            msgs = history_messages.copy()
            if current_message:
                msgs.append(current_message)
            
            # 如果消息列表为空，直接返回
            if not msgs:
                logger.warning(f"[节点 {node_name}] 消息列表为空，跳过执行")
                return state
            
            # 执行Agent，传入消息列表和系统消息
            result = await agent_executor.ainvoke(
                msgs=msgs,
                callbacks=None,
                sys_msg=sys_msg
            )
            
            # 更新状态
            new_state = state.copy()
            
            # 关键：每次创建新 state 时，edges_var 使用新字典，不继承原始值
            # 确保上游节点的数据不会污染下游节点的条件判断
            new_state["edges_var"] = {}
            
            if "output" in result:
                # AgentExecutor 返回 output 与可选的 output_data（当 LLM 返回的 content 已是 dict 时）
                output = result["output"]
                output_data = result.get("output_data")

                # 通用化数据提取：不区分节点名称，统一处理所有节点
                # 数据来源1：output_data 为 dict 时直接使用（如豆包等接口直接返回结构化 content）
                # 数据来源2：output 为 str 时尝试 JSON 解析（整段或括号匹配截取）
                try:
                    if isinstance(output_data, dict):
                        # 已结构化，直接写入 edges_var
                        _apply_output_data_to_edges_var(output_data, new_state["edges_var"])
                        logger.debug(
                            f"[节点 {node_name}] 从 output_data(dict) 提取数据到 edges_var: {list(new_state['edges_var'].keys())}"
                        )
                    elif isinstance(output, str) and output.strip():
                        # 字符串：先整段解析，失败则按括号匹配截取根对象再解析
                        parsed = _parse_json_from_output_string(output)
                        if isinstance(parsed, dict):
                            _apply_output_data_to_edges_var(parsed, new_state["edges_var"])
                            logger.debug(
                                f"[节点 {node_name}] 从输出字符串解析到 edges_var: {list(new_state['edges_var'].keys())}"
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
                    # 解析失败不影响流程继续，edges_var 保持空
                
                # 按 config 将 edges_var 指定 key 覆盖到 persistence_edges_var（持久化通道，透传到任意下级节点）
                # 必须 .copy()：new_state=state.copy() 是浅拷贝，直接改 new_state["persistence_edges_var"][k] 会污染上游 state
                persist_keys = config_dict.get("persist_to_persistence_edges_var")
                if isinstance(persist_keys, list) and len(persist_keys) > 0:
                    new_state["persistence_edges_var"] = (state.get("persistence_edges_var") or {}).copy()
                    for k in persist_keys:
                        if k in new_state["edges_var"]:
                            new_state["persistence_edges_var"][k] = new_state["edges_var"][k]
                    logger.debug(
                        f"[节点 {node_name}] 将 edges_var 的 key 同步到 persistence_edges_var: {persist_keys}"
                    )
                
                # 将AI回复存放到 flow_msgs（由 add_messages reducer 追加），不存放到 history_messages
                ai_message = AIMessage(content=output)
                new_state["flow_msgs"] = [ai_message]
                # history_messages 保持不变，不添加中间节点的输出
            
            return new_state
        
        return agent_node_action
