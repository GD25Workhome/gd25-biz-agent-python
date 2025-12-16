"""
路由节点实现
"""
from langchain_core.messages import BaseMessage

from domain.router.state import RouterState
from domain.router.tools.router_tools import identify_intent


def route_node(state: RouterState) -> RouterState:
    """
    路由节点：根据意图路由到对应的智能体
    
    Args:
        state: 路由状态
        
    Returns:
        更新后的路由状态
    """
    # 如果已经确定了智能体且不需要重新路由，直接返回
    if state.get("current_agent") and not state.get("need_reroute", False):
        return state
    
    # 识别意图
    intent_result = identify_intent.invoke({"messages": state["messages"]})
    
    # 根据意图确定智能体
    intent_type = intent_result.get("intent_type", "unclear")
    
    if intent_type == "blood_pressure":
        state["current_intent"] = "blood_pressure"
        state["current_agent"] = "blood_pressure_agent"
        state["need_reroute"] = False
    elif intent_type == "appointment":
        state["current_intent"] = "appointment"
        state["current_agent"] = "appointment_agent"
        state["need_reroute"] = False
    else:
        state["current_intent"] = "unclear"
        state["current_agent"] = None
        state["need_reroute"] = False
    
    return state

