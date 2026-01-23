"""
节点创建器注册表
使用单例模式管理节点创建器
"""
import logging
from typing import Dict

from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition

logger = logging.getLogger(__name__)


class NodeCreatorRegistry:
    """节点创建器注册表（单例模式）"""
    
    _instance: 'NodeCreatorRegistry' = None
    _creators: Dict[str, NodeCreator] = {}
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, node_type: str, creator: NodeCreator) -> None:
        """
        注册节点创建器
        
        Args:
            node_type: 节点类型（如 "agent"、"function"）
            creator: 节点创建器实例
        """
        self._creators[node_type] = creator
        logger.info(f"注册节点创建器: {node_type} -> {creator.__class__.__name__}")
    
    def create_node(self, node_def: NodeDefinition, flow_def: FlowDefinition):
        """
        创建节点函数
        
        Args:
            node_def: 节点定义
            flow_def: 流程定义
            
        Returns:
            Callable: 节点函数
            
        Raises:
            ValueError: 如果节点类型未注册
        """
        creator = self._creators.get(node_def.type)
        if not creator:
            raise ValueError(f"不支持的节点类型: {node_def.type}，已注册的类型: {list(self._creators.keys())}")
        
        return creator.create(node_def, flow_def)
    
    def get_creator(self, node_type: str) -> NodeCreator:
        """
        获取节点创建器
        
        Args:
            node_type: 节点类型
            
        Returns:
            NodeCreator: 节点创建器实例，如果不存在则返回None
        """
        return self._creators.get(node_type)
    
    def get_all_types(self) -> list:
        """
        获取所有已注册的节点类型
        
        Returns:
            list: 节点类型列表
        """
        return list(self._creators.keys())


# 创建全局注册表实例
node_creator_registry = NodeCreatorRegistry()


# 模块加载时自动注册默认的节点创建器
def _init_default_creators():
    """初始化默认的节点创建器"""
    from backend.domain.flows.nodes.agent_creator import AgentNodeCreator
    from backend.domain.flows.nodes.function_creator import FunctionNodeCreator
    from backend.domain.flows.nodes.embedding_creator import EmbeddingNodeCreator
    
    node_creator_registry.register("agent", AgentNodeCreator())
    node_creator_registry.register("function", FunctionNodeCreator())
    node_creator_registry.register("em_agent", EmbeddingNodeCreator())
    logger.info("已注册默认节点创建器: agent, function, em_agent")


# 自动初始化
_init_default_creators()
