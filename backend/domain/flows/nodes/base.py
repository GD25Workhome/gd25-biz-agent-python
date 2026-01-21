"""
节点创建器抽象基类
"""
from abc import ABC, abstractmethod
from typing import Callable

from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition


class NodeCreator(ABC):
    """节点创建器抽象基类"""
    
    @abstractmethod
    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
        创建节点函数
        
        Args:
            node_def: 节点定义
            flow_def: 流程定义
            
        Returns:
            Callable: 节点函数（异步函数，接收 FlowState，返回 FlowState）
        """
        pass
