"""
图构建器
负责构建LangGraph图
"""
import logging
from typing import Dict, Callable, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.domain.state import FlowState, FlowInputSchema, FlowOutputSchema
from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition
from backend.domain.flows.condition_evaluator import ConditionEvaluator
from backend.domain.flows.nodes.registry import node_creator_registry

logger = logging.getLogger(__name__)


class GraphBuilder:
    """图构建器"""
    
    @staticmethod
    def build_graph(flow_def: FlowDefinition) -> StateGraph:
        """
            根据 flow.yaml 解析结果构建 LangGraph StateGraph（未 compile）。

            依次注册节点、按源节点挂载 always 边或条件边，并设置 entry_node；
            编译与检查点由 FlowManager 在 compile 阶段完成。

            Args:
                flow_def: 流程定义（节点、边、入口节点）

            Returns:
                StateGraph: 已挂载节点与边的图，待 compile

            Raises:
                ValueError: 同一源节点同时存在条件边与 always 边
        """
        # 1. 创建 StateGraph，约束对外输入/输出 schema
        graph = StateGraph(
            FlowState,
            input_schema=FlowInputSchema,
            output_schema=FlowOutputSchema,
        )

        # 2. 遍历 flow_def.nodes，注册各类型节点函数
        for node_def in flow_def.nodes:
            # _create_node_function：经 node_creator_registry 按 type 创建 agent/function 等节点
            node_func = GraphBuilder._create_node_function(node_def, flow_def)
            graph.add_node(node_def.name, node_func)

        # 3. 按 from 节点分组边，便于同一出点挂载条件路由或普通边
        edges_by_from: Dict[str, List] = {}
        for edge in flow_def.edges:
            if edge.from_node not in edges_by_from:
                edges_by_from[edge.from_node] = []
            edges_by_from[edge.from_node].append(edge)

        # 4. 逐源节点添加边（条件边与普通边互斥）
        for from_node, edges in edges_by_from.items():
            conditional_edges = [e for e in edges if e.condition != "always"]
            always_edges = [e for e in edges if e.condition == "always"]

            if conditional_edges and always_edges:
                raise ValueError(f"节点 {from_node} 同时包含条件边和普通边，不支持")

            if conditional_edges:
                # 4a. 条件边：按 state 评估表达式，返回首个匹配的目标节点
                # edges_list 用默认参数传入 route_func，避免循环闭包捕获同一变量名
                edges_list = conditional_edges.copy()

                def route_func(state: FlowState, edges_list=edges_list):
                    """按边条件顺序评估，返回首个为真的目标节点名或 END。"""
                    for edge in edges_list:
                        # _evaluate_condition：委托 ConditionEvaluator 解析 intent 等 state 变量
                        if GraphBuilder._evaluate_condition(edge.condition, state):
                            if edge.to_node == "END":
                                return END
                            return edge.to_node
                    return END

                route_map = {}
                for edge in conditional_edges:
                    target = END if edge.to_node == "END" else edge.to_node
                    route_map[target] = target
                route_map[END] = END

                graph.add_conditional_edges(from_node, route_func, route_map)
            else:
                # 4b. 普通边：固定跳转至下一节点或 END
                for edge in always_edges:
                    target = END if edge.to_node == "END" else edge.to_node
                    graph.add_edge(edge.from_node, target)

        # 5. 设置流程入口并返回未编译图
        graph.set_entry_point(flow_def.entry_node)

        logger.info(f"成功构建流程图: {flow_def.name}")
        return graph
    
    @staticmethod
    def _create_node_function(node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
            委托节点创建器注册表，按 node_def.type 生成可执行的节点函数。

            Args:
                node_def: 节点定义（name、type、config）
                flow_def: 所属流程定义（供节点读取 flow_dir 等）

            Returns:
                Callable: 异步节点函数 (state) -> state

            Raises:
                ValueError: 节点类型未在注册表中登记
        """
        return node_creator_registry.create_node(node_def, flow_def)

    @staticmethod
    def _evaluate_condition(condition: str, state: FlowState) -> bool:
        """
            评估 flow.yaml 边条件表达式是否为真。

            Args:
                condition: 条件字符串（如 intent == 'blood_pressure' && confidence >= 0.8）
                state: 当前流程状态（edges_var / persistence_edges_var 供表达式引用）

            Returns:
                bool: 条件成立为 True，否则 False
        """
        return ConditionEvaluator.evaluate(condition, state)

