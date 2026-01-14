"""
图构建器
负责构建LangGraph图
"""
import logging
from typing import Dict, Callable, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.domain.state import FlowState
from backend.domain.flows.definition import FlowDefinition, NodeDefinition
from backend.domain.flows.condition_evaluator import ConditionEvaluator
from backend.domain.agents.factory import AgentFactory
from backend.domain.tools.registry import tool_registry

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
                # 关键修复：使用默认参数避免闭包问题
                # 问题：Python 闭包捕获的是变量名，不是变量值
                # 在循环中，所有 route_func 都引用同一个变量名 edges_list
                # 当循环继续执行时，edges_list 被重新赋值，所有闭包都看到新值
                # 解决方案：使用默认参数，默认参数在函数定义时求值，可以"冻结"值
                edges_list = conditional_edges.copy()
                
                def route_func(state: FlowState, edges_list=edges_list):
                    """路由函数"""
                    for edge in edges_list:
                        if GraphBuilder._evaluate_condition(edge.condition, state):
                            # 如果目标是字符串 "END"，转换为 END 对象
                            if edge.to_node == "END":
                                return END
                            return edge.to_node
                    return END
                
                # 构建路由映射
                route_map = {}
                for edge in conditional_edges:
                    # 如果目标是字符串 "END"，转换为 END 对象
                    target = END if edge.to_node == "END" else edge.to_node
                    route_map[target] = target
                
                # 确保 END 在路由映射中（即使没有显式使用）
                route_map[END] = END
                
                graph.add_conditional_edges(from_node, route_func, route_map)
            else:
                # 普通边
                for edge in always_edges:
                    # 如果目标是字符串 "END"，转换为 END 对象
                    target = END if edge.to_node == "END" else edge.to_node
                    graph.add_edge(edge.from_node, target)
        
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
            node_name = node_def.name
            
            async def agent_node_action(state: FlowState) -> FlowState:
                """Agent节点函数"""
                from langchain_core.messages import AIMessage
                from backend.infrastructure.prompts.sys_prompt_builder import build_system_message
                
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
                    # AgentExecutor返回output字段
                    output = result["output"]
                    import json
                    
                    # 通用化数据提取：不区分节点名称，统一处理所有节点
                    # 检查两个数据来源：JSON所有属性 + additional_fields
                    try:
                        if isinstance(output, str):
                            # 尝试从输出中提取 JSON
                            json_start = output.find("{")
                            json_end = output.rfind("}") + 1
                            if json_start >= 0 and json_end > json_start:
                                json_str = output[json_start:json_end]
                                output_data = json.loads(json_str)
                                
                                # 数据来源1：如果是 JSON 类型，直接将所有属性存储到 edges_var
                                # 跳过非边条件判断相关的字段（如 response_content, reasoning_summary）
                                if isinstance(output_data, dict):
                                    for key, value in output_data.items():
                                        if key not in ["response_content", "reasoning_summary"]:
                                            new_state["edges_var"][key] = value
                                
                                # 数据来源2：如果存在 additional_fields，将其中的所有字段也存储到 edges_var
                                if "additional_fields" in output_data:
                                    additional_fields = output_data["additional_fields"]
                                    if isinstance(additional_fields, dict):
                                        for key, value in additional_fields.items():
                                            new_state["edges_var"][key] = value
                                
                                logger.debug(
                                    f"[节点 {node_name}] 从输出提取数据到 edges_var: {new_state['edges_var']}"
                                )
                    except Exception as e:
                        logger.debug(f"[节点 {node_name}] 解析输出 JSON 失败（可能不是 JSON 格式）: {e}")
                        # 不是 JSON 格式或解析失败，不影响流程继续
                    
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
        - 状态变量：所有存储在 state.edges_var 中的变量都可以在条件表达式中使用
        
        Args:
            condition: 条件表达式（如 "intent == 'blood_pressure' && confidence >= 0.8"）
            state: 流程状态
            
        Returns:
            bool: 条件是否为真
        """
        return ConditionEvaluator.evaluate(condition, state)

