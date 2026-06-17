"""
Embedding 节点创建器

将 flow.yaml 中 type=em_agent 的节点编译为：从 edges_var 读文本 → 调 Embedding 模型 → 写回向量。
"""
import logging
from typing import Callable, List

from typing_extensions import override

from backend.domain.state import FlowState
from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition, EmbeddingNodeConfig, ModelConfig
from backend.domain.embeddings.factory import EmbeddingFactory

logger = logging.getLogger(__name__)


class EmbeddingNodeCreator(NodeCreator):
    """
        将 flow.yaml 的 em_agent 节点编译为闭包形式的异步 embedding 节点函数。

        编译期创建 EmbeddingExecutor；运行期从 edges_var 指定字段读取文本并写回向量。
    """

    @override
    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
            实现 NodeCreator.create：解析 em_agent 配置并返回 embedding_node_action。

            Args:
                node_def: flow.yaml 中的 em_agent 节点（config.model/input/output）
                flow_def: 所属流程定义（保留以符合基类契约）

            Returns:
                Callable: 异步节点函数 embedding_node_action(state) -> state
        """
        config_dict = node_def.config
        model_config = ModelConfig(**config_dict["model"])
        embedding_config = EmbeddingNodeConfig(
            model=model_config,
            input=config_dict["input"],
            output=config_dict["output"],
        )

        # EmbeddingFactory.create_embedding_executor：按 provider 创建向量模型执行器
        embedding_executor = EmbeddingFactory.create_embedding_executor(
            config=embedding_config,
        )

        input_field = embedding_config.input["filed"]
        output_field = embedding_config.output["filed"]
        node_name = node_def.name

        async def embedding_node_action(state: FlowState) -> FlowState:
            """
                单次 Embedding 节点执行：读 edges_var → 调模型 → 写 edges_var 向量字段。

                edges_var 每轮重置，避免污染下游条件边。
            """
            edges_var = state.get("edges_var", {})
            input_text = edges_var.get(input_field)

            if input_text is None:
                error_msg = (
                    f"[节点 {node_name}] 输入字段 '{input_field}' 不存在于 edges_var 中，"
                    f"当前 edges_var: {edges_var}"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

            if isinstance(input_text, str):
                texts: List[str] = [input_text]
            elif isinstance(input_text, list):
                texts = input_text
            else:
                error_msg = (
                    f"[节点 {node_name}] 输入数据类型不支持: {type(input_text)}, "
                    f"期望 str 或 List[str]，实际值: {input_text}"
                )
                logger.error(error_msg)
                raise TypeError(error_msg)

            try:
                embeddings = await embedding_executor.ainvoke(texts)
                logger.debug(
                    f"[节点 {node_name}] 成功生成 {len(embeddings)} 个向量，"
                    f"向量维度: {len(embeddings[0]) if embeddings else 0}"
                )
            except Exception as e:
                error_msg = f"[节点 {node_name}] 调用 embedding 模型失败: {e}"
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e

            if isinstance(input_text, str):
                embedding_value = embeddings[0] if embeddings else []
            else:
                embedding_value = embeddings

            new_state = state.copy()
            new_state["edges_var"] = {}
            new_state["edges_var"][output_field] = embedding_value

            logger.debug(
                f"[节点 {node_name}] 将 embedding 结果保存到 edges_var['{output_field}']"
            )

            return new_state

        return embedding_node_action
