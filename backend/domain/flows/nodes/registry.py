"""
节点创建器注册表

GraphBuilder 编译 flow.yaml 时，按节点 type 从此注册表查找 NodeCreator 并生成节点函数。
模块 import 时自动注册 agent、function、em_agent、rag_agent 四类默认创建器。
"""
import logging
from typing import Callable, Dict, List, Optional

from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition

logger = logging.getLogger(__name__)


class NodeCreatorRegistry:
    """
        节点创建器注册表（单例）。

        维护 node_type → NodeCreator 映射，供 GraphBuilder 在构建 StateGraph 时
        将 flow.yaml 中的节点定义转换为可执行的 async 节点函数。
    """

    _instance: Optional["NodeCreatorRegistry"] = None
    _creators: Dict[str, NodeCreator] = {}

    def __new__(cls) -> "NodeCreatorRegistry":
        """保证全局仅存在一个注册表实例。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, node_type: str, creator: NodeCreator) -> None:
        """
            登记一种 flow.yaml 节点 type 与其创建器实例。

            Args:
                node_type: 节点类型字符串（如 agent、function）
                creator: 实现 NodeCreator.create 的创建器实例
        """
        self._creators[node_type] = creator
        logger.info(f"注册节点创建器: {node_type} -> {creator.__class__.__name__}")

    def create_node(
        self,
        node_def: NodeDefinition,
        flow_def: FlowDefinition,
    ) -> Callable:
        """
            根据节点定义创建 LangGraph 节点函数。

            Args:
                node_def: flow.yaml 解析出的单节点配置（name、type、config）
                flow_def: 所属流程定义（供创建器读取 flow_dir 等）

            Returns:
                Callable: 异步节点函数 (state) -> state

            Raises:
                ValueError: node_def.type 未在注册表中登记
        """
        creator = self._creators.get(node_def.type)
        if not creator:
            raise ValueError(
                f"不支持的节点类型: {node_def.type}，已注册的类型: {list(self._creators.keys())}"
            )

        return creator.create(node_def, flow_def)

    def get_creator(self, node_type: str) -> Optional[NodeCreator]:
        """
            按 type 查询已登记的创建器。

            Args:
                node_type: 节点类型字符串

            Returns:
                对应的 NodeCreator 实例；未登记时返回 None
        """
        return self._creators.get(node_type)

    def get_all_types(self) -> List[str]:
        """
            返回当前已登记的全部节点 type 列表。

            Returns:
                节点类型字符串列表
        """
        return list(self._creators.keys())


# 全局单例，供 GraphBuilder 与模块内 _init_default_creators 使用
node_creator_registry = NodeCreatorRegistry()


def _init_default_creators() -> None:
    """
        模块加载时注册内置节点创建器，避免 GraphBuilder 遇到未知 type。

        新增节点类型时：实现 NodeCreator 子类并在此 register，或于其它模块 import 后调用 register。
    """
    from backend.domain.flows.nodes.agent_creator import AgentNodeCreator
    from backend.domain.flows.nodes.function_creator import FunctionNodeCreator
    from backend.domain.flows.nodes.embedding_creator import EmbeddingNodeCreator
    from backend.domain.flows.nodes.rag_agent_creator import RagAgentNodeCreator

    # 1. 登记四类内置 type → 创建器
    node_creator_registry.register("agent", AgentNodeCreator())
    node_creator_registry.register("function", FunctionNodeCreator())
    node_creator_registry.register("em_agent", EmbeddingNodeCreator())
    node_creator_registry.register("rag_agent", RagAgentNodeCreator())
    logger.info("已注册默认节点创建器: agent, function, em_agent, rag_agent")


# 模块 import 时完成默认注册
_init_default_creators()
