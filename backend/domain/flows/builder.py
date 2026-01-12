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

                # 获取当前用户消息
                current_message = state.get("current_message")
                if not current_message:
                    return state
                
                input_text = current_message.content if hasattr(current_message, "content") else str(current_message)
                
                # 执行Agent，传入替换后的系统提示词
                result = agent_executor.invoke(
                    {"input": input_text},
                    callbacks=None,
                    system_prompt=system_prompt
                )
                
                # 更新状态（？？是不是解析模型的回复结果，如果是，这里需要将其抽取成为一个独立的方法）（？？为何要用新的state）
                new_state = state.copy()
                if "output" in result:
                    # AgentExecutor返回output字段
                    output = result["output"]
                    # 如果是意图识别节点，解析JSON并更新intent
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
                                    new_state["intent"] = intent_data.get("intent", "unclear")
                        except Exception as e:
                            logger.warning(f"解析意图识别结果失败: {e}")
                            new_state["intent"] = "unclear"
                    
                    # 将输出添加到历史消息列表
                    # 将当前消息和AI回复都添加到历史消息中
                    from langchain_core.messages import AIMessage
                    history_messages = state.get("history_messages", [])
                    ai_message = AIMessage(content=output)
                    
                    # 更新历史消息：添加当前消息和AI回复
                    new_history = history_messages.copy()
                    if current_message:
                        new_history.append(current_message)
                    new_history.append(ai_message)
                    
                    new_state["history_messages"] = new_history
                    # 清空当前消息（已处理，因为 total=False，可以设置为 None）
                    new_state["current_message"] = None
                
                return new_state
            
            return agent_node_action
        
        else:
            # 其他类型的节点（本版本不支持）
            raise ValueError(f"不支持的节点类型: {node_def.type}")
    
    @staticmethod
    def _evaluate_condition(condition: str, state: FlowState) -> bool:
        """
        评估条件表达式（简化版，仅支持简单的条件判断）
        
        Args:
            condition: 条件表达式（如 "intent == 'blood_pressure'"）
            state: 流程状态
            
        Returns:
            bool: 条件是否为真
        """
        # 简化处理：仅支持 intent == "xxx" 的条件
        if "==" in condition:
            parts = condition.split("==")
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip().strip('"\'')
                
                if key == "intent":
                    return state.get("intent") == value
        
        # 默认返回False
        return False

