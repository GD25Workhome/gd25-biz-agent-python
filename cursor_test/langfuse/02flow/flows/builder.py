"""
图构建器
负责构建LangGraph图
关键：包含节点函数创建逻辑，在运行时创建Langfuse Handler
"""
import logging
from typing import Dict, Callable, List
from langgraph.graph import StateGraph, END

from core.state import FlowState
from core.definition import FlowDefinition, NodeDefinition, AgentNodeConfig, ModelConfig
from agents.factory import AgentFactory

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
        
        # 创建节点函数字典
        node_functions: Dict[str, Callable] = {}
        
        # 为每个节点创建节点函数
        for node_def in flow_def.nodes:
            node_func = GraphBuilder._create_node_function(node_def, flow_def)
            node_functions[node_def.name] = node_func
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
        
        关键：在运行时从ContextVar获取trace_id，创建Handler
        
        Args:
            node_def: 节点定义
            flow_def: 流程定义
            
        Returns:
            Callable: 节点函数
        """
        if node_def.type == "agent":
            # Agent节点
            
            # 解析节点配置
            config_dict = node_def.config
            model_config = ModelConfig(**config_dict["model"])
            agent_config = AgentNodeConfig(
                prompt=config_dict["prompt"],  # 简化版：直接是字符串
                model=model_config,
                tools=config_dict.get("tools")
            )
            
            # 创建Agent（编译时）
            agent_executor = AgentFactory.create_agent(
                config=agent_config,
                flow_dir=flow_def.flow_dir or ""
            )
            
            # 创建节点函数（编译时）
            # 捕获节点名称，用于意图识别节点的特殊处理
            node_name = node_def.name
            
            def agent_node(state: FlowState) -> FlowState:
                """Agent节点函数（运行时执行）"""
                # 获取最后一条用户消息
                if not state.get("messages"):
                    return state
                
                last_message = state["messages"][-1]
                input_text = last_message.content if hasattr(last_message, "content") else str(last_message)
                
                # 关键：在节点执行时从ContextVar获取trace_id，创建Handler
                # 此时ContextVar应该有值（在API层已设置）
                from langfuse_local.handler import (
                    get_current_trace_id, create_langfuse_handler, get_langfuse_client
                )
                
                trace_id = get_current_trace_id()
                callbacks = []
                
                # 创建子 span 并设置节点名称（关键！）
                langfuse_client = get_langfuse_client()
                
                if trace_id:
                    # 创建Langfuse Handler（会从ContextVar获取trace_id）
                    langfuse_handler = create_langfuse_handler()
                    if langfuse_handler:
                        callbacks.append(langfuse_handler)
                        logger.debug(
                            f"[Agent节点] 从ContextVar获取trace_id={trace_id}, "
                            f"创建Langfuse Handler并传递给Agent调用"
                        )
                    else:
                        logger.warning(
                            f"[Agent节点] trace_id={trace_id} 存在，但创建Langfuse Handler失败"
                        )
                else:
                    logger.warning(
                        f"[Agent节点] 无法从ContextVar获取trace_id，"
                        f"将使用编译时创建的Handler（可能创建新的Trace）"
                    )
                
                # 创建子 span，使用节点名称作为 span name（关键！）
                # 这样在 Langfuse UI 中可以看到每个节点的名称
                result = None
                if langfuse_client and trace_id:
                    try:
                        # 使用 with 语句创建子 span，确保在节点执行期间 span 处于活动状态
                        with langfuse_client.start_as_current_span(
                            name=node_name,
                            metadata={"node_type": "agent", "node_name": node_name}
                        ):
                            logger.debug(f"[Agent节点] 创建子 span: name={node_name}, trace_id={trace_id}")
                            
                            # 执行Agent，传递运行时callbacks（关键！）
                            result = agent_executor.invoke(
                                {"input": input_text},
                                callbacks=callbacks if callbacks else None
                            )
                    except Exception as e:
                        logger.warning(f"[Agent节点] 创建子 span 失败，直接执行: {e}", exc_info=True)
                        # 如果创建 span 失败，仍然执行 Agent
                        result = agent_executor.invoke(
                            {"input": input_text},
                            callbacks=callbacks if callbacks else None
                        )
                else:
                    # 如果没有 langfuse_client 或 trace_id，直接执行
                    result = agent_executor.invoke(
                        {"input": input_text},
                        callbacks=callbacks if callbacks else None
                    )
                
                # 更新状态
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
                    
                    # 将输出添加到消息列表
                    from langchain_core.messages import AIMessage
                    new_state["messages"] = state["messages"] + [AIMessage(content=output)]
                
                return new_state
            
            return agent_node
        
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

