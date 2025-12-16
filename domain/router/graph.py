"""
路由图构建
"""
from typing import Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from psycopg_pool import AsyncConnectionPool

from domain.router.state import RouterState
from domain.router.node import route_node
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
    
    # 添加智能体节点（动态添加）
    # 血压记录智能体
    blood_pressure_agent = AgentFactory.create_agent("blood_pressure_agent")
    workflow.add_node("blood_pressure_agent", blood_pressure_agent)
    
    # 复诊管理智能体
    appointment_agent = AgentFactory.create_agent("appointment_agent")
    workflow.add_node("appointment_agent", appointment_agent)
    
    # 设置入口点
    workflow.set_entry_point("route")
    
    # 添加条件边：从路由节点根据意图路由到智能体或结束
    def route_to_agent(state: RouterState) -> str:
        """根据当前意图路由到对应的智能体"""
        current_agent = state.get("current_agent")
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
            END: END
        }
    )
    
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

