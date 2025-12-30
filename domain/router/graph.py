"""
路由图构建
"""
import logging
from typing import Optional, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from langchain_core.messages import SystemMessage
from psycopg_pool import AsyncConnectionPool

from domain.router.state import RouterState
from domain.router.node import route_node, clarify_intent_node
from domain.agents.factory import AgentFactory
from domain.agents.registry import AgentRegistry
from infrastructure.prompts.manager import PromptManager
from infrastructure.prompts.placeholder import PlaceholderManager
from infrastructure.prompts.template_loader import AgentTemplateLoader
from infrastructure.observability.llm_logger import LlmLogContext
from infrastructure.observability.langfuse_handler import get_langfuse_client, normalize_langfuse_trace_id
from app.core.config import settings

logger = logging.getLogger(__name__)

# 提示词管理器实例（单例）
_prompt_manager = PromptManager()


def _load_agent_template(agent_key: str) -> str:
    """
    加载 Agent 的原始提示词模板（包含占位符）
    
    使用统一的提示词加载服务，避免代码重复。
    
    Args:
        agent_key: Agent键名
        
    Returns:
        提示词模板内容（包含占位符）
    """
    # 获取 Agent 配置
    if not AgentFactory._config:
        AgentFactory.load_config()
    
    agent_config = AgentFactory._config.get(agent_key, {})
    if not agent_config:
        raise ValueError(f"Agent配置不存在: {agent_key}")
    
    # 使用统一的提示词加载服务
    return AgentTemplateLoader.load_template(agent_key, agent_config)


def create_router_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    pool: Optional[AsyncConnectionPool] = None,
    store: Optional[BaseStore] = None,
):
    """
    创建路由图
    
    Args:
        checkpointer: 检查点保存器（用于状态持久化）
        pool: 数据库连接池
        store: 存储（用于长期记忆）
        
    Returns:
        CompiledGraph: 已编译的路由图
    """
    # 创建状态图
    workflow = StateGraph(RouterState)
    
    # 添加路由节点
    workflow.add_node("route", route_node)
    
    # 添加澄清节点
    workflow.add_node("clarify_intent", clarify_intent_node)
    
    # 注入用户上下文的包装器，向 LLM 显式提供 user_id
    def with_user_context(agent_node, agent_name: str):
        """
        为智能体包装系统指令，动态注入完整的上下文信息。
        
        方案三：运行时动态替换系统消息中的占位符
        - 从 state 中获取所有占位符值
        - 加载原始提示词模板
        - 填充占位符，生成完整的系统消息
        - 替换或添加系统消息到消息列表
        """
        async def _run(state: RouterState) -> RouterState:
            messages = state.get("messages", [])
            user_id = state.get("user_id")
            session_id = state.get("session_id")
            
            logger.info(
                f"[AGENT_CONTEXT] 开始处理系统消息: {agent_name}, "
                f"session_id={session_id}, user_id={user_id}"
            )
            
            # 1. 从 state 中获取所有占位符值
            placeholders = PlaceholderManager.get_placeholders(agent_name, state=state)
            logger.debug(
                f"[AGENT_CONTEXT] 获取占位符值: {agent_name}, "
                f"占位符数量: {len(placeholders)}, "
                f"包含: {list(placeholders.keys())}"
            )
            
            # 2. 加载原始提示词模板（包含占位符）
            try:
                template = _load_agent_template(agent_name)
                logger.debug(f"[AGENT_CONTEXT] 加载提示词模板成功: {agent_name}")
            except Exception as e:
                logger.error(f"[AGENT_CONTEXT] 加载提示词模板失败: {agent_name}, 错误: {str(e)}")
                raise ValueError(f"无法加载提示词模板: {agent_name}, 错误: {str(e)}")
            
            # 3. 填充占位符，生成完整的系统提示词
            filled_prompt = PlaceholderManager.fill_placeholders(template, placeholders)
            
            # 检查是否还有未填充的占位符
            import re
            remaining_placeholders = re.findall(r'\{\{(\w+)\}\}', filled_prompt)
            if remaining_placeholders:
                logger.warning(
                    f"[AGENT_CONTEXT] 系统消息中仍有未填充的占位符: {agent_name}, "
                    f"占位符: {remaining_placeholders}"
                )
            else:
                logger.debug(f"[AGENT_CONTEXT] 所有占位符已成功填充: {agent_name}")
            
            # 4. 创建系统消息（包含完整的上下文信息）
            system_message = SystemMessage(content=filled_prompt)
            
            # 5. 处理消息列表：移除旧的系统消息（如果存在），添加新的系统消息
            # 移除包含占位符的系统消息（Agent 创建时注入的）
            filtered_messages = [
                msg for msg in messages
                if not isinstance(msg, SystemMessage) or
                not (hasattr(msg, 'content') and '{{' in str(msg.content))
            ]
            
            # 在消息列表开头插入新的系统消息
            messages_with_context = [system_message] + filtered_messages
            
            logger.info(
                f"[AGENT_CONTEXT] 系统消息注入完成: {agent_name}, "
                f"session_id={session_id}, user_id={user_id}, "
                f"消息总数: {len(messages_with_context)}"
            )
            
            # 6. 调用 Agent
            logger.info(
                f"[AGENT_INVOKE] 调用智能体: {agent_name}, "
                f"session_id={session_id}, user_id={user_id}, "
                f"messages_count={len(messages_with_context)}"
            )
            
            # 构建日志上下文，用于 LLM 调用日志
            log_context = LlmLogContext(
                session_id=session_id,
                user_id=user_id,
                agent_key=agent_name,
                trace_id=state.get("trace_id"),
                conversation_id=session_id  # 使用 session_id 作为 conversation_id
            )
            
            # 注意：由于 Agent 在创建时已经创建了 LLM 实例，我们无法在运行时修改其日志上下文
            # 但日志回调处理器会在调用时自动记录，只是缺少上下文信息
            # 这里记录日志，说明即将调用 Agent（可能会触发 LLM 调用）
            logger.info(
                f"[AGENT_LLM] 即将调用智能体，可能会触发LLM调用: {agent_name}, "
                f"session_id={session_id}, user_id={user_id}"
            )
            
            # 获取 trace_id
            trace_id = state.get("trace_id")
            
            # 创建 Langfuse Span 追踪（如果启用）
            langfuse_client = get_langfuse_client()
            # 检查是否启用 Span 追踪（支持通过配置禁用）
            if (settings.LANGFUSE_ENABLED and 
                settings.LANGFUSE_ENABLE_SPANS and 
                langfuse_client and 
                trace_id):
                # 将 trace_id 转换为 Langfuse 要求的格式（32 个小写十六进制字符）
                normalized_trace_id = normalize_langfuse_trace_id(trace_id)
                
                # 构建 span 参数，显式指定 trace_id
                # 注意：
                # 1. session_id 和 user_id 已在 Trace 级别设置，会自动继承，不需要在 Span 中重复传递
                # 2. agent_key 在 input 中已有，不需要在 metadata 中重复
                span_params = {
                    "name": f"agent_{agent_name}",
                    "input": {
                        "agent_key": agent_name,
                        "messages_count": len(messages_with_context),
                        # 移除 user_id 和 session_id（已在 Trace 级别设置）
                    },
                    "metadata": {
                        # 移除 agent_key（已在 input 中）
                        # 移除 session_id 和 user_id（已在 Trace 级别设置）
                        "intent_type": state.get("current_intent"),
                    },
                }
                # 尝试使用 trace_context 参数指定 trace_id（如果 SDK 支持）
                # 注意：Langfuse SDK 要求 trace_id 必须是 32 个小写十六进制字符
                try:
                    span_params["trace_context"] = {"trace_id": normalized_trace_id}
                    # 使用 Span 追踪 Agent 节点执行
                    with langfuse_client.start_as_current_span(**span_params):
                        result = await agent_node.ainvoke({"messages": messages_with_context})
                except (TypeError, AttributeError, ValueError) as e:
                    # 如果 SDK 不支持 trace_context 参数或格式不正确，记录警告并使用默认方式
                    logger.warning(
                        f"Langfuse SDK 可能不支持 trace_context 参数或 trace_id 格式不正确，将使用默认行为。"
                        f"trace_id={normalized_trace_id}, error={str(e)}"
                    )
                    # 移除 trace_context 参数，使用默认方式
                    span_params.pop("trace_context", None)
                    try:
                        with langfuse_client.start_as_current_span(**span_params):
                            result = await agent_node.ainvoke({"messages": messages_with_context})
                    except Exception as span_error:
                        # 错误隔离：Span 创建失败不影响主流程
                        logger.warning(
                            f"创建 Langfuse Span 失败: {span_error}，继续执行主流程"
                        )
                        result = await agent_node.ainvoke({"messages": messages_with_context})
                except Exception as e:
                    # 错误隔离：Span 创建失败不影响主流程
                    logger.warning(f"创建 Langfuse Span 失败: {e}，继续执行主流程")
                    result = await agent_node.ainvoke({"messages": messages_with_context})
            else:
                # Langfuse 未启用、Span 追踪被禁用或 trace_id 不存在，直接执行
                result = await agent_node.ainvoke({"messages": messages_with_context})
            
            # 保留路由状态中的关键字段，防止下游节点丢失上下文
            # 注意：不再保留 bp_form，让 LLM 从对话历史中自己理解
            for key in ("session_id", "user_id", "current_intent", "current_agent", "need_reroute", "trace_id"):
                if key in state and key not in result:
                    result[key] = state[key]
            
            return result
        
        _run.__name__ = f"{agent_name}_with_user_context"
        return _run
    
    # ===== 动态构建路由图 =====
    # 核心原则：Agent在路由图创建时一次性创建
    
    # 从Agent注册表获取所有Agent
    agent_registry = AgentRegistry.get_all_agents()
    agent_node_names = {}  # agent_key -> node_name 映射
    agent_intent_map = {}  # intent_type -> node_name 映射（用于路由决策）
    
    # 动态创建Agent节点（在路由图创建时一次性创建）
    for agent_key, agent_config in agent_registry.items():
        # 创建Agent实例（在路由图创建时一次性创建）
        agent = AgentFactory.create_agent(agent_key)
        
        # 获取节点名称（从配置或使用agent_key）
        node_name = AgentRegistry.get_agent_node_name(agent_key)
        agent_node_names[agent_key] = node_name
        
        # 获取意图类型（用于路由决策）
        intent_type = AgentRegistry.get_agent_intent_type(agent_key)
        if intent_type:
            agent_intent_map[intent_type] = node_name
        
        # 添加Agent节点（使用with_user_context包装）
        workflow.add_node(node_name, with_user_context(agent, agent_key))
        logger.info(f"添加Agent节点: {node_name} (agent_key: {agent_key}, intent_type: {intent_type})")
    
    # 设置入口点
    workflow.set_entry_point("route")
    
    # 动态路由决策
    def route_to_agent(state: RouterState) -> str:
        """
        根据当前意图路由到对应的Agent
        
        核心原则：Agent在路由图创建时一次性创建，这里只是路由决策
        """
        # 防止死循环：如果最后一条消息是AI消息，说明没有新的用户消息，应该结束
        messages = state.get("messages", [])
        if messages:
            from langchain_core.messages import AIMessage
            last_message = messages[-1]
            if isinstance(last_message, AIMessage):
                # 最后一条消息是AI消息，没有新的用户输入，结束流程
                return END
        
        current_intent = state.get("current_intent")
        current_agent = state.get("current_agent")
        need_reroute = state.get("need_reroute", False)
        
        # 如果不需要重新路由，且已经有智能体，直接结束（等待下一轮用户输入）
        if not need_reroute and current_agent:
            return END
        
        # 如果意图不明确，且需要重新路由，路由到澄清节点
        if need_reroute and (current_intent == "unclear" or not current_agent):
            return "clarify_intent"
        
        # 根据智能体路由（动态查找）
        if current_agent:
            # 通过agent_key查找节点名称
            node_name = agent_node_names.get(current_agent)
            if node_name:
                return node_name
        
        # 如果current_agent不存在，尝试通过intent_type查找
        if current_intent and current_intent in agent_intent_map:
            return agent_intent_map[current_intent]
        
        # 如果都找不到，结束流程
        return END
    
    # 动态构建路由映射
    route_map = {name: name for name in agent_node_names.values()}
    route_map["clarify_intent"] = "clarify_intent"
    route_map[END] = END
    
    workflow.add_conditional_edges("route", route_to_agent, route_map)
    
    # 澄清节点执行后返回路由节点（回边）
    workflow.add_edge("clarify_intent", "route")
    
    # 动态添加回边（Agent执行后返回路由节点）
    for node_name in agent_node_names.values():
        workflow.add_edge(node_name, "route")
    
    # 编译图
    graph_config = {}
    if checkpointer:
        graph_config["checkpointer"] = checkpointer
    if store:
        graph_config["store"] = store
    
    return workflow.compile(**graph_config)
    
    