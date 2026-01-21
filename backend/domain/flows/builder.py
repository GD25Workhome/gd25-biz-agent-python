"""
图构建器
负责构建LangGraph图
"""
import logging
from typing import Dict, Callable, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.domain.state import FlowState
from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition
from backend.domain.flows.condition_evaluator import ConditionEvaluator
from backend.domain.flows.nodes.registry import node_creator_registry

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
        
        使用节点创建器注册表来创建不同类型的节点函数。
        支持通过注册表动态扩展新的节点类型。
        
        Args:
            node_def: 节点定义
            flow_def: 流程定义
            
        Returns:
            Callable: 节点函数
            
        Raises:
            ValueError: 如果节点类型未注册
        """
        return node_creator_registry.create_node(node_def, flow_def)
    
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

