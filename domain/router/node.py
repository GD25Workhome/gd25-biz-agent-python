"""
路由节点实现
"""
import logging
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from domain.router.state import RouterState, IntentResult
from domain.router.tools.router_tools import identify_intent, clarify_intent
from domain.agents.registry import AgentRegistry
from app.core.config import settings

logger = logging.getLogger(__name__)


def route_node(state: RouterState) -> RouterState:
    """
    路由节点：根据意图路由到对应的智能体
    
    功能：
    1. 防止无限循环：如果最后一条消息是AI消息，停止执行
    2. 意图识别：识别用户意图
    3. 意图变化检测：检测意图是否发生变化
    4. 路由决策：根据意图路由到对应智能体或澄清节点
    
    Args:
        state: 路由状态
        
    Returns:
        更新后的路由状态
    """
    # 获取消息列表
    messages = state.get("messages", [])
    if not messages:
        logger.warning("路由节点: 没有消息，返回未更新状态")
        return state
    
    # 防止无限循环：如果最后一条消息是AI消息，说明没有新的用户消息，应该停止执行
    # 这可以防止无限循环：router -> agent -> router -> ... 或 router -> clarify_intent -> router -> ...
    last_message = messages[-1]
    if isinstance(last_message, AIMessage):
        logger.info("路由节点: 最后一条消息是AI消息，没有新的用户消息，停止路由执行")
        # 重要：设置 need_reroute=False，防止 route_to_agent 继续路由
        state["need_reroute"] = False
        return state  # 直接返回，不进行路由决策
    
    # 获取当前意图和智能体
    current_intent = state.get("current_intent")
    current_agent = state.get("current_agent")
    
    # 识别意图
    try:
        intent_result_dict = identify_intent.invoke({"messages": messages})
        intent_result = IntentResult(**intent_result_dict)
        
        logger.info(
            f"路由节点: 意图识别结果 - type={intent_result.intent_type}, "
            f"confidence={intent_result.confidence}, "
            f"need_clarification={intent_result.need_clarification}"
        )
        
        new_intent = intent_result.intent_type
        new_agent = None
        
        # 根据意图动态确定智能体（使用AgentRegistry）
        if new_intent and new_intent != "unclear":
            # 从AgentRegistry查找对应意图类型的Agent
            agent_registry = AgentRegistry.get_all_agents()
            for agent_key, agent_config in agent_registry.items():
                routing_config = agent_config.get("routing", {})
                intent_type = routing_config.get("intent_type")
                if intent_type == new_intent:
                    new_agent = agent_key
                    break
        
        # 如果找不到对应的Agent，设置为None（unclear意图）
        if not new_agent and new_intent != "unclear":
            logger.warning(f"路由节点: 未找到对应意图 '{new_intent}' 的Agent，设置为None")
            new_agent = None
        
        # 意图变化检测
        intent_changed = False
        if current_intent != new_intent:
            intent_changed = True
            logger.info(
                f"路由节点: 检测到意图变化 - 从 '{current_intent}' 变为 '{new_intent}'"
            )
        
        # 检查是否需要重新路由
        need_reroute = False
        has_new_user_input = isinstance(last_message, HumanMessage)
        
        # 如果意图不明确或需要澄清，需要路由到澄清节点
        if new_intent == "unclear" or intent_result.need_clarification:
            need_reroute = True
            logger.info("路由节点: 意图不明确或需要澄清，将路由到澄清节点")
        # 如果意图发生变化，需要重新路由
        elif intent_changed:
            need_reroute = True
            logger.info("路由节点: 意图发生变化，需要重新路由")
        # 如果当前没有智能体，需要路由
        elif not current_agent:
            need_reroute = True
            logger.info("路由节点: 当前没有智能体，需要路由")
        # 如果智能体发生变化，需要重新路由
        elif current_agent != new_agent:
            need_reroute = True
            logger.info(
                f"路由节点: 智能体发生变化 - 从 '{current_agent}' 变为 '{new_agent}'"
            )

        # 关键修正：只要检测到新的用户输入，就应再次执行当前智能体流程，避免新消息被直接 END 掉
        if has_new_user_input:
            need_reroute = True
            logger.info("路由节点: 检测到新的用户输入，强制重新路由以执行当前智能体")
        
        # 更新状态
        state["current_intent"] = new_intent
        state["current_agent"] = new_agent
        state["need_reroute"] = need_reroute
        
        return state
        
    except Exception as e:
        logger.error(f"路由节点执行失败: {str(e)}", exc_info=True)
        # 发生错误时，设置为 unclear 意图
        state["current_intent"] = "unclear"
        state["current_agent"] = None
        state["need_reroute"] = True
        return state


def clarify_intent_node(state: RouterState) -> RouterState:
    """
    意图澄清节点：当意图不明确时，生成澄清问题
    
    Args:
        state: 路由状态
        
    Returns:
        更新后的路由状态（添加澄清问题消息）
    """
    messages = state.get("messages", [])
    if not messages:
        logger.warning("澄清节点: 没有消息，返回未更新状态")
        return state
    
    # 获取最后一条用户消息
    last_message = messages[-1]
    user_query = ""
    
    if isinstance(last_message, HumanMessage):
        user_query = last_message.content if hasattr(last_message, 'content') else str(last_message)
    elif hasattr(last_message, 'content'):
        user_query = str(last_message.content)
    else:
        user_query = str(last_message)
    
    # 调用澄清工具
    try:
        clarification = clarify_intent.invoke({"query": user_query})
        
        logger.info(f"澄清节点: 生成澄清问题: {clarification}")
        
        # 添加澄清问题到消息列表
        updated_messages = list(messages)
        updated_messages.append(AIMessage(content=clarification))
        
        # 更新状态
        state["messages"] = updated_messages
        state["need_reroute"] = True  # 澄清后需要重新路由
        
        return state
        
    except Exception as e:
        logger.error(f"澄清节点执行失败: {str(e)}", exc_info=True)
        # 返回默认澄清问题
        default_clarification = "抱歉，我没有理解您的意图。请告诉我您是想记录血压、预约复诊、记录健康事件、记录用药、记录症状，还是需要其他帮助？"
        
        updated_messages = list(messages)
        updated_messages.append(AIMessage(content=default_clarification))
        
        state["messages"] = updated_messages
        state["need_reroute"] = True
        
        return state

