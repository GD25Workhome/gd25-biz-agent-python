"""
Function节点创建器
使用注册表机制创建Function节点
"""
import logging
from typing import Callable

from backend.domain.state import FlowState
from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition
from backend.domain.flows.nodes.function_registry import function_registry

logger = logging.getLogger(__name__)


class FunctionNodeCreator(NodeCreator):
    """Function节点创建器"""
    
    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
        创建Function节点函数
        
        从节点配置中读取 function_key，从注册表中获取对应的节点类并实例化。
        节点名称与函数实现完全解耦，通过配置的key灵活指定。
        
        Args:
            node_def: 节点定义
            flow_def: 流程定义
            
        Returns:
            Callable: Function节点函数（异步函数）
            
        Raises:
            ValueError: 如果配置中缺少 function_key 或节点未注册
        """
        # 确保相关模块已导入，以便__init_subclass__自动注册节点
        # 然后发现所有已注册的节点（懒加载）
        try:
            # 导入implementations模块，触发__init_subclass__自动注册
            import backend.domain.flows.implementations  # noqa: F401
        except ImportError:
            # 如果模块不存在，继续执行（可能节点在其他位置定义）
            pass
        
        # 发现所有已导入的子类
        function_registry.discover()
        
        node_name = node_def.name
        config = node_def.config or {}
        
        # 从配置中读取 function_key（必需）
        function_key = config.get("function_key")
        if not function_key:
            raise ValueError(
                f"节点 {node_name} 的配置中缺少 function_key。"
                f"请在 flow.yaml 的 config 中配置 function_key，例如："
                f"config:\n  function_key: 'retrieval_node'"
            )
        
        logger.debug(f"使用配置中的节点key: {node_name} -> {function_key}")
        
        # 从注册表中获取节点类
        node_class = function_registry.get(function_key)
        if not node_class:
            available_keys = function_registry.get_all_keys()
            raise ValueError(
                f"未找到Function节点: {function_key}。"
                f"节点名称: {node_name}。"
                f"可用的节点key: {available_keys if available_keys else '无'}"
            )
        
        # 实例化节点
        node_instance = node_class()
        
        # 返回节点的execute方法（已经是异步函数）
        return node_instance.execute
