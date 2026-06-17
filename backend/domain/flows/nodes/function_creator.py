"""
Function 节点创建器

将 flow.yaml 中 type=function 的节点按 function_key 委托给 function_registry 中的实现类。
"""
import logging
from typing import Callable

from typing_extensions import override

from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition
from backend.domain.flows.nodes.function_registry import function_registry

logger = logging.getLogger(__name__)


class FunctionNodeCreator(NodeCreator):
    """
        将 flow.yaml 的 function 节点绑定到 function_registry 中的 BaseFunctionNode 实现。

        节点名（name）与实现 key（function_key）解耦，由 config.function_key 指定。
    """

    @override
    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
            实现 NodeCreator.create：按 function_key 实例化函数节点并返回其 execute 方法。

            Args:
                node_def: flow.yaml 中的 function 节点（config.function_key 必填）
                flow_def: 所属流程定义（当前实现未直接使用，保留以符合基类契约）

            Returns:
                Callable: 异步节点函数 execute(state) -> state

            Raises:
                ValueError: 缺少 function_key 或 registry 中无对应实现
        """
        # 1. 触发 implementations 模块 import，完成 BaseFunctionNode 子类自注册
        try:
            import backend.domain.flows.implementations  # noqa: F401
        except ImportError:
            pass

        # function_registry.discover：扫描已 import 的子类并登记 function_key
        function_registry.discover()

        node_name = node_def.name
        config = node_def.config or {}

        # 2. 校验 function_key
        function_key = config.get("function_key")
        if not function_key:
            raise ValueError(
                f"节点 {node_name} 的配置中缺少 function_key。"
                f"请在 flow.yaml 的 config 中配置 function_key，例如："
                f"config:\n  function_key: 'retrieval_node'"
            )

        logger.debug(f"使用配置中的节点key: {node_name} -> {function_key}")

        # 3. 从注册表取实现类并实例化
        node_class = function_registry.get(function_key)
        if not node_class:
            available_keys = function_registry.get_all_keys()
            raise ValueError(
                f"未找到Function节点: {function_key}。"
                f"节点名称: {node_name}。"
                f"可用的节点key: {available_keys if available_keys else '无'}"
            )

        node_instance = node_class()
        node_instance._config = config

        return node_instance.execute
