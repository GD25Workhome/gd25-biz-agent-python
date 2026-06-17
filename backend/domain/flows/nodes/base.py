"""
节点创建器抽象基类

GraphBuilder 按 flow.yaml 节点 type 查找 NodeCreator 实现，调用 create 生成 LangGraph 节点函数。
子类实现 create 时应使用 typing_extensions.override 标明重写。
"""
from abc import ABC, abstractmethod
from typing import Callable

from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition


class NodeCreator(ABC):
    """
        节点创建器抽象基类。

        每种 flow.yaml 节点 type（agent、function 等）对应一个 NodeCreator 子类，
        在 NodeCreatorRegistry 中注册后供 GraphBuilder 编译流程图时使用。
    """

    @abstractmethod
    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
            将单节点定义编译为 LangGraph 可执行的异步节点函数。

            子类须使用 @override 装饰此方法，并保持签名一致。

            Args:
                node_def: flow.yaml 解析出的节点（name、type、config）
                flow_def: 所属流程定义（flow_dir 等）

            Returns:
                Callable: 异步节点函数 (state: FlowState) -> FlowState
        """
        pass
