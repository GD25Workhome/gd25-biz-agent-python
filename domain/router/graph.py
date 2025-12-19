"""
路由图构建
"""
import logging
import re
from typing import Optional, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from langchain_core.messages import SystemMessage, HumanMessage
from psycopg_pool import AsyncConnectionPool

from domain.router.state import RouterState, BloodPressureForm
from domain.router.node import route_node, clarify_intent_node
from domain.agents.factory import AgentFactory
from infrastructure.prompts.manager import PromptManager
from infrastructure.observability.llm_logger import LlmLogContext

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
    
    # ===== 血压表单槽位抽取 =====
    def _extract_bp_form(messages, existing: Optional[BloodPressureForm] = None) -> BloodPressureForm:
        """
        从用户消息中解析收缩压、舒张压、心率，形成显式槽位，避免重复询问。
        """
        form: BloodPressureForm = dict(existing or {})
        
        # 避免重复覆盖已有值
        systolic = form.get("systolic")
        diastolic = form.get("diastolic")
        heart_rate = form.get("heart_rate")
        
        # 定义正则模式
        systolic_pattern = re.compile(r"(收缩压|高压)[^0-9]{0,3}(\d{2,3})")
        diastolic_pattern = re.compile(r"(舒张压|低压)[^0-9]{0,3}(\d{2,3})")
        heart_rate_pattern = re.compile(r"(心率|脉搏)[^0-9]{0,3}(\d{2,3})")
        pair_pattern = re.compile(r"(\d{2,3})\s*/\s*(\d{2,3})")
        
        for msg in messages:
            if not isinstance(msg, HumanMessage):
                continue
            content = msg.content if hasattr(msg, "content") else str(msg)
            
            # 120/80 形式优先解析
            if (systolic is None or diastolic is None):
                pair_match = pair_pattern.search(content)
                if pair_match:
                    if systolic is None:
                        systolic = int(pair_match.group(1))
                    if diastolic is None:
                        diastolic = int(pair_match.group(2))
            
            if systolic is None:
                s_match = systolic_pattern.search(content)
                if s_match:
                    systolic = int(s_match.group(2))
            
            if diastolic is None:
                d_match = diastolic_pattern.search(content)
                if d_match:
                    diastolic = int(d_match.group(2))
            
            if heart_rate is None:
                h_match = heart_rate_pattern.search(content)
                if h_match:
                    heart_rate = int(h_match.group(2))
        
        if systolic is not None:
            form["systolic"] = systolic
        if diastolic is not None:
            form["diastolic"] = diastolic
        if heart_rate is not None:
            form["heart_rate"] = heart_rate
        
        return form
    
    def _build_bp_context_hint(user_id: str, form: BloodPressureForm) -> str:
        """
        生成血压表单上下文提示，列出已收集与待收集字段。
        
        注意：此函数保留用于fallback，优先使用PromptManager构建提示词。
        """
        collected = []
        missing = []
        if "systolic" in form:
            collected.append(f"收缩压={form['systolic']}")
        else:
            missing.append("收缩压")
        if "diastolic" in form:
            collected.append(f"舒张压={form['diastolic']}")
        else:
            missing.append("舒张压")
        if "heart_rate" in form:
            collected.append(f"心率={form['heart_rate']}")
        if "record_time" in form:
            collected.append(f"记录时间={form['record_time']}")
        if "notes" in form:
            collected.append("备注已填写")
        
        collected_text = "；".join(collected) if collected else "无"
        missing_text = "、".join(missing) if missing else "无（必填项已齐全，可直接调用 record_blood_pressure）"
        
        return (
            f"系统提供的用户ID：{user_id}。"
            f"已收集字段：{collected_text}。"
            f"待补全字段（必填优先）：{missing_text}。"
            "请只询问缺失字段，字段齐全时直接调用 record_blood_pressure 工具，不要重复询问已提供的数据。"
        )
    
    # 注入用户上下文的包装器，避免 LLM 反复向用户询问 user_id，并提供显式槽位
    def with_user_context(agent_node, agent_name: str):
        """
        为智能体包装系统指令，向 LLM 显式提供 user_id，并在工具调用前做槽位校验。
        """
        def _normalize_user_id(raw_user_id: Any) -> Optional[str]:
            """
            将 user_id 规范化为不超过 50 字符的字符串，若无效返回 None。
            """
            if raw_user_id is None:
                return None
            try:
                user_text = str(raw_user_id).strip()
                if not user_text:
                    return None
                return user_text[:50]
            except Exception:
                return None

        async def _run(state: RouterState) -> RouterState:
            messages = state.get("messages", [])
            user_id = state.get("user_id")
            bp_form: BloodPressureForm = state.get("bp_form", {}) if agent_name == "blood_pressure_agent" else {}
            
            # 仅血压智能体需要显式槽位抽取
            if agent_name == "blood_pressure_agent":
                bp_form = _extract_bp_form(messages, bp_form)
                state["bp_form"] = bp_form
                logger.info(f"[BP_SLOT] 已抽取表单: {bp_form}")
            
            # 仅在存在 user_id 且未注入过时添加系统提示，避免重复插入
            has_context = any(
                isinstance(msg, SystemMessage) and "系统提供的用户ID" in msg.content
                for msg in messages
            )
            if user_id and not has_context:
                # 使用PromptManager构建用户信息提示
                try:
                    # 构建上下文数据
                    context = {"user_id": user_id}
                    
                    if agent_name == "blood_pressure_agent":
                        # 血压智能体需要表单信息
                        collected = []
                        missing = []
                        if "systolic" in bp_form:
                            collected.append(f"收缩压={bp_form['systolic']}")
                        else:
                            missing.append("收缩压")
                        if "diastolic" in bp_form:
                            collected.append(f"舒张压={bp_form['diastolic']}")
                        else:
                            missing.append("舒张压")
                        if "heart_rate" in bp_form:
                            collected.append(f"心率={bp_form['heart_rate']}")
                        if "record_time" in bp_form:
                            collected.append(f"记录时间={bp_form['record_time']}")
                        if "notes" in bp_form:
                            collected.append("备注已填写")
                        
                        context["collected_fields"] = "；".join(collected) if collected else "无"
                        context["missing_fields"] = "、".join(missing) if missing else "无（必填项已齐全，可直接调用 record_blood_pressure）"
                    
                    # 使用PromptManager渲染user_info模块
                    user_info_prompt = _prompt_manager.render(
                        agent_key=agent_name,
                        context=context,
                        include_modules=["user_info"]
                    )
                    
                    if user_info_prompt:
                        system_hint = SystemMessage(content=user_info_prompt)
                        messages = [system_hint, *messages]
                        logger.info(f"[AGENT_HINT] 使用PromptManager注入系统提示: {agent_name}")
                    else:
                        # 如果PromptManager返回空，使用fallback
                        logger.warning(f"PromptManager返回空提示词，使用fallback: {agent_name}")
                        if agent_name == "blood_pressure_agent":
                            hint_content = _build_bp_context_hint(user_id, bp_form)
                        else:
                            hint_content = (
                                f"系统提供的用户ID：{user_id}。"
                                "调用工具时直接使用该 user_id，无需向用户索取。"
                            )
                        system_hint = SystemMessage(content=hint_content)
                        messages = [system_hint, *messages]
                        logger.info(f"[AGENT_HINT] 使用fallback注入系统提示: {agent_name}")
                        
                except (FileNotFoundError, ValueError) as e:
                    # 如果模板不存在，使用fallback
                    logger.warning(f"提示词模板加载失败，使用fallback: {agent_name}, 错误: {str(e)}")
                    if agent_name == "blood_pressure_agent":
                        hint_content = _build_bp_context_hint(user_id, bp_form)
                    else:
                        hint_content = (
                            f"系统提供的用户ID：{user_id}。"
                            "调用工具时直接使用该 user_id，无需向用户索取。"
                        )
                    system_hint = SystemMessage(content=hint_content)
                    messages = [system_hint, *messages]
                    logger.info(f"[AGENT_HINT] 使用fallback注入系统提示: {agent_name}")
            
            # 直接调用 Agent，由 LLM 决定如何回复和是否调用工具
            # 不再进行硬编码的槽位校验和工具调用，完全由 LLM 根据系统提示词来决策
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
            
            result = await agent_node.ainvoke({"messages": messages})
            
            # 保留路由状态中的关键字段，防止下游节点丢失上下文
            for key in ("session_id", "user_id", "current_intent", "current_agent", "need_reroute", "bp_form"):
                if key in state and key not in result:
                    result[key] = state[key]
            
            return result
        
        _run.__name__ = f"{agent_name}_with_user_context"
        return _run
    
    # 添加智能体节点（动态添加，并包裹用户上下文）
    blood_pressure_agent = AgentFactory.create_agent("blood_pressure_agent")
    workflow.add_node("blood_pressure_agent", with_user_context(blood_pressure_agent, "blood_pressure_agent"))
    
    appointment_agent = AgentFactory.create_agent("appointment_agent")
    workflow.add_node("appointment_agent", with_user_context(appointment_agent, "appointment_agent"))
    
    # 添加健康事件Agent节点
    health_event_agent = AgentFactory.create_agent("health_event_agent")
    workflow.add_node("health_event_agent", with_user_context(health_event_agent, "health_event_agent"))
    
    # 添加用药记录Agent节点
    medication_agent = AgentFactory.create_agent("medication_agent")
    workflow.add_node("medication_agent", with_user_context(medication_agent, "medication_agent"))
    
    # 添加症状记录Agent节点
    symptom_agent = AgentFactory.create_agent("symptom_agent")
    workflow.add_node("symptom_agent", with_user_context(symptom_agent, "symptom_agent"))
    
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
        elif current_agent == "health_event_agent":
            return "health_event_agent"
        elif current_agent == "medication_agent":
            return "medication_agent"
        elif current_agent == "symptom_agent":
            return "symptom_agent"
        else:
            return END
    
    workflow.add_conditional_edges(
        "route",
        route_to_agent,
        {
            "blood_pressure_agent": "blood_pressure_agent",
            "appointment_agent": "appointment_agent",
            "health_event_agent": "health_event_agent",
            "medication_agent": "medication_agent",
            "symptom_agent": "symptom_agent",
            "clarify_intent": "clarify_intent",
            END: END,
        },
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
    
    