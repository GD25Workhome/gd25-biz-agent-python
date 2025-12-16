"""
路由图构建
"""
from typing import Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from psycopg_pool import AsyncConnectionPool

from domain.router.state import RouterState
from domain.router.node import route_node, clarify_intent_node
from domain.agents.factory import AgentFactory


def create_router_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    pool: Optional[AsyncConnectionPool] = None,
    store: Optional[BaseStore] = None
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
    
    # 添加智能体节点（动态添加）
    # 血压记录智能体
    blood_pressure_agent = AgentFactory.create_agent("blood_pressure_agent")
    workflow.add_node("blood_pressure_agent", blood_pressure_agent)
    
    # 复诊管理智能体
    appointment_agent = AgentFactory.create_agent("appointment_agent")
    workflow.add_node("appointment_agent", appointment_agent)
    
    # 设置入口点
    workflow.set_entry_point("route")
    
    # 添加条件边：从路由节点根据意图路由到智能体、澄清节点或结束
    def route_to_agent(state: RouterState) -> str:
        """根据当前意图路由到对应的智能体或澄清节点"""
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
        
        # 根据智能体路由
        if current_agent == "blood_pressure_agent":
            return "blood_pressure_agent"
        elif current_agent == "appointment_agent":
            return "appointment_agent"
        else:
            return END
    
    workflow.add_conditional_edges(
        "route",
        route_to_agent,
        {
            "blood_pressure_agent": "blood_pressure_agent",
            "appointment_agent": "appointment_agent",
            "clarify_intent": "clarify_intent",
            END: END
        }
    )
    
    # 澄清节点执行后返回路由节点（回边）
    workflow.add_edge("clarify_intent", "route")
    
    # 智能体执行后返回路由节点（支持多轮对话）
    workflow.add_edge("blood_pressure_agent", "route")
    workflow.add_edge("appointment_agent", "route")
    
    # 编译图
    graph_config = {}
    if checkpointer:
        graph_config["checkpointer"] = checkpointer
    if store:
        graph_config["store"] = store
    
    return workflow.compile(**graph_config)

