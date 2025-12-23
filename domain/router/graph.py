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
from infrastructure.observability.llm_logger import LlmLogContext
from infrastructure.observability.langfuse_handler import get_langfuse_client

logger = logging.getLogger(__name__)

# 提示词管理器实例（单例）
_prompt_manager = PromptManager()


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
        为智能体包装系统指令，向 LLM 显式提供 user_id。
        
        注意：不再进行硬编码的槽位提取和填充，完全依赖 LLM 根据提示词和对话历史自主处理。
        LLM 可以通过 LangGraph 的 checkpointer 机制访问完整的对话历史，从而理解上下文。
        """
        async def _run(state: RouterState) -> RouterState:
            messages = state.get("messages", [])
            user_id = state.get("user_id")
            
            # 仅在存在 user_id 且未注入过时添加系统提示，避免重复插入
            has_context = any(
                isinstance(msg, SystemMessage) and "系统提供的用户ID" in msg.content
                for msg in messages
            )
            if user_id and not has_context:
                # 使用PromptManager构建用户信息提示
                try:
                    # 构建上下文数据（只提供 user_id，让 LLM 自己从对话历史中理解上下文）
                    context = {"user_id": user_id}
                    
                    # 使用PromptManager渲染user_info模块
                    user_info_prompt = _prompt_manager.render(
                        agent_key=agent_name,
                        context=context,
                        include_modules=["user_info"]
                    )
                    
                    if not user_info_prompt:
                        raise ValueError(f"PromptManager返回空提示词: {agent_name}")
                    
                    system_hint = SystemMessage(content=user_info_prompt)
                    messages = [system_hint, *messages]
                    logger.info(f"[AGENT_HINT] 使用PromptManager注入系统提示: {agent_name}")
                        
                except (FileNotFoundError, ValueError) as e:
                    # 如果模板不存在，直接抛出异常
                    logger.error(f"提示词模板加载失败: {agent_name}, 错误: {str(e)}")
                    raise ValueError(f"无法加载提示词模板: {agent_name}, 错误: {str(e)}")
            
            # 直接调用 Agent，由 LLM 决定如何回复和是否调用工具
            # LLM 可以通过 LangGraph 的 checkpointer 机制访问完整的对话历史
            # 提示词已经明确告诉 LLM 如何理解上下文、提取数据和判断完整性
            session_id = state.get("session_id")
            logger.info(
                f"[AGENT_INVOKE] 调用智能体: {agent_name}, "
                f"session_id={session_id}, user_id={user_id}, "
                f"messages_count={len(messages)}"
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
            
            # 创建 Langfuse Span 追踪（如果启用）
            langfuse_client = get_langfuse_client()
            if langfuse_client:
                # 使用 Span 追踪 Agent 节点执行
                with langfuse_client.start_as_current_span(
                    name=f"agent_{agent_name}",
                    input={
                        "agent_key": agent_name,
                        "messages_count": len(messages),
                        "user_id": user_id,
                        "session_id": session_id,
                    },
                    metadata={
                        "agent_key": agent_name,
                        "session_id": session_id,
                        "user_id": user_id,
                        "intent_type": state.get("current_intent"),
                    }
                ):
                    result = await agent_node.ainvoke({"messages": messages})
            else:
                # Langfuse 未启用，直接执行
                result = await agent_node.ainvoke({"messages": messages})
            
            # 保留路由状态中的关键字段，防止下游节点丢失上下文
            # 注意：不再保留 bp_form，让 LLM 从对话历史中自己理解
            for key in ("session_id", "user_id", "current_intent", "current_agent", "need_reroute"):
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
    
    