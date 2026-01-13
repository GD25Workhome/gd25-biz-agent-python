"""
图构建器
负责构建LangGraph图
"""
import logging
import re
from typing import Dict, Callable, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.domain.state import FlowState
from backend.domain.flows.definition import FlowDefinition, NodeDefinition
from backend.domain.flows.condition_evaluator import ConditionEvaluator
from backend.domain.agents.factory import AgentFactory
from backend.domain.tools.registry import tool_registry
from backend.infrastructure.prompts.manager import prompt_manager

logger = logging.getLogger(__name__)


class GraphBuilder:
    """图构建器"""
    
    @staticmethod
    def build_graph(flow_def: FlowDefinition) -> StateGraph:
        """
        构建LangGraph图
        
        Args:
            flow_def: 流程定义
            
        Returns:
            StateGraph: 构建的图
        """
        graph = StateGraph(FlowState)
        
        # 为每个节点创建节点函数
        for node_def in flow_def.nodes:
            node_func = GraphBuilder._create_node_function(node_def, flow_def)
            graph.add_node(node_def.name, node_func)
        
        # 按源节点分组边
        edges_by_from: Dict[str, List] = {}
        for edge in flow_def.edges:
            if edge.from_node not in edges_by_from:
                edges_by_from[edge.from_node] = []
            edges_by_from[edge.from_node].append(edge)
        
        # 添加边
        for from_node, edges in edges_by_from.items():
            # 检查是否有条件边（非always的边）
            conditional_edges = [e for e in edges if e.condition != "always"]
            always_edges = [e for e in edges if e.condition == "always"]
            
            if conditional_edges and always_edges:
                # 混合情况：既有条件边又有普通边（不支持，报错）
                raise ValueError(f"节点 {from_node} 同时包含条件边和普通边，不支持")
            
            if conditional_edges:
                # 条件边：创建路由函数
                # 使用列表捕获，避免闭包问题
                edges_list = conditional_edges.copy()
                
                def route_func(state: FlowState) -> str:
                    """路由函数"""
                    for edge in edges_list:
                        if GraphBuilder._evaluate_condition(edge.condition, state):
                            return edge.to_node
                    return END
                
                # 构建路由映射
                route_map = {edge.to_node: edge.to_node for edge in conditional_edges}
                route_map[END] = END
                
                graph.add_conditional_edges(from_node, route_func, route_map)
            else:
                # 普通边
                for edge in always_edges:
                    graph.add_edge(edge.from_node, edge.to_node)
        
        # 设置入口节点
        graph.set_entry_point(flow_def.entry_node)
        
        logger.info(f"成功构建流程图: {flow_def.name}")
        return graph
    
    @staticmethod
    def _create_node_function(node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
        创建节点函数
        
        Args:
            node_def: 节点定义
            flow_def: 流程定义
            
        Returns:
            Callable: 节点函数
        """
        if node_def.type == "agent":
            # Agent节点
            from backend.domain.flows.definition import AgentNodeConfig, ModelConfig
            
            # 解析节点配置
            config_dict = node_def.config
            model_config = ModelConfig(**config_dict["model"])
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
            # 捕获节点名称，用于意图识别节点的特殊处理
            node_name = node_def.name
            
            def agent_node_action(state: FlowState) -> FlowState:
                """Agent节点函数"""
                from langchain_core.messages import SystemMessage, AIMessage
                
                # 获取系统提示词，然后替换占位符
                system_prompt = prompt_manager.get_prompt_by_key(agent_executor.prompt_cache_key)
                # 用FlowState user_info 属性替换提示词中的 {{user_info}} 占位符
                user_info = state.get("user_info")
                if user_info:
                    # 替换 {{user_info}} 占位符（使用正则表达式支持灵活格式）
                    system_prompt = re.sub(r'\{\{user_info\}\}', user_info, system_prompt)
                else:
                    # 如果 user_info 为空，替换为空字符串
                    system_prompt = re.sub(r'\{\{user_info\}\}', "", system_prompt)
                
                # 将系统提示词封装为 SystemMessage
                sys_msg = SystemMessage(content=system_prompt)
                
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
                result = agent_executor.invoke(
                    msgs=msgs,
                    callbacks=None,
                    sys_msg=sys_msg
                )
                
                # 更新状态
                new_state = state.copy()
                if "output" in result:
                    # AgentExecutor返回output字段
                    output = result["output"]
                    # 如果是意图识别节点，解析JSON并更新intent、confidence、need_clarification
                    if node_name == "intent_recognition":
                        import json
                        try:
                            # 尝试从输出中提取JSON
                            if isinstance(output, str):
                                # 查找JSON部分
                                json_start = output.find("{")
                                json_end = output.rfind("}") + 1
                                if json_start >= 0 and json_end > json_start:
                                    json_str = output[json_start:json_end]
                                    intent_data = json.loads(json_str)
                                    
                                    # 提取意图
                                    new_state["intent"] = intent_data.get("intent", "unclear")
                                    
                                    # 提取置信度
                                    confidence = intent_data.get("confidence")
                                    if confidence is not None:
                                        try:
                                            new_state["confidence"] = float(confidence)
                                        except (ValueError, TypeError):
                                            logger.warning(f"置信度格式错误: {confidence}，使用默认值 0.0")
                                            new_state["confidence"] = 0.0
                                    else:
                                        new_state["confidence"] = 0.0
                                    
                                    # 提取是否需要澄清
                                    need_clarification = intent_data.get("need_clarification")
                                    if need_clarification is not None:
                                        new_state["need_clarification"] = bool(need_clarification)
                                    else:
                                        new_state["need_clarification"] = False
                                    
                                    logger.debug(
                                        f"意图识别结果: intent={new_state['intent']}, "
                                        f"confidence={new_state['confidence']}, "
                                        f"need_clarification={new_state['need_clarification']}"
                                    )
                        except Exception as e:
                            logger.warning(f"解析意图识别结果失败: {e}")
                            new_state["intent"] = "unclear"
                            new_state["confidence"] = 0.0
                            new_state["need_clarification"] = False
                    
                    # 将AI回复存放到 flow_msgs（流程中间消息），不存放到 history_messages
                    ai_message = AIMessage(content=output)
                    flow_msgs = state.get("flow_msgs", [])
                    new_flow_msgs = flow_msgs.copy()
                    new_flow_msgs.append(ai_message)
                    new_state["flow_msgs"] = new_flow_msgs
                    # history_messages 保持不变，不添加中间节点的输出
                
                return new_state
            
            return agent_node_action
        
        else:
            # 其他类型的节点（本版本不支持）
            raise ValueError(f"不支持的节点类型: {node_def.type}")
    
    @staticmethod
    def _evaluate_condition(condition: str, state: FlowState) -> bool:
        """
        评估条件表达式
        
        使用 ConditionEvaluator 来评估复杂的条件表达式，支持：
        - 逻辑运算符：&& (and), || (or)
        - 比较运算符：==, !=, <, <=, >, >=
        - 状态变量：intent, confidence, need_clarification
        
        Args:
            condition: 条件表达式（如 "intent == 'blood_pressure' && confidence >= 0.8"）
            state: 流程状态
            
        Returns:
            bool: 条件是否为真
        """
        return ConditionEvaluator.evaluate(condition, state)

