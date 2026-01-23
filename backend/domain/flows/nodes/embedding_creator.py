"""
Embedding节点创建器
"""
import logging
from typing import Callable

from backend.domain.state import FlowState
from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition, EmbeddingNodeConfig, ModelConfig
from backend.domain.embeddings.factory import EmbeddingFactory

logger = logging.getLogger(__name__)


class EmbeddingNodeCreator(NodeCreator):
    """Embedding节点创建器"""
    
    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
        创建Embedding节点函数
        
        Args:
            node_def: 节点定义
            flow_def: 流程定义
            
        Returns:
            Callable: Embedding节点函数（异步函数）
        """
        # 解析节点配置
        config_dict = node_def.config
        model_config = ModelConfig(**config_dict["model"])
        embedding_config = EmbeddingNodeConfig(
            model=model_config,
            input=config_dict["input"],
            output=config_dict["output"]
        )
        
        # 创建 Embedding 执行器（使用工厂模式，与 AgentNodeCreator 保持一致）
        embedding_executor = EmbeddingFactory.create_embedding_executor(
            config=embedding_config
        )
        
        # 提取配置
        input_field = embedding_config.input["filed"]
        output_field = embedding_config.output["filed"]
        node_name = node_def.name
        
        # 创建节点函数
        async def embedding_node_action(state: FlowState) -> FlowState:
            """Embedding节点函数"""
            # 从 state.edges_var 读取输入数据
            edges_var = state.get("edges_var", {})
            input_text = edges_var.get(input_field)
            
            # 输入数据缺失：抛出异常，中断流程执行
            if input_text is None:
                error_msg = (
                    f"[节点 {node_name}] 输入字段 '{input_field}' 不存在于 edges_var 中，"
                    f"当前 edges_var: {edges_var}"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # 处理输入：支持字符串和列表
            if isinstance(input_text, str):
                texts = [input_text]
            elif isinstance(input_text, list):
                texts = input_text
            else:
                # 输入数据类型错误：抛出异常，中断流程执行
                error_msg = (
                    f"[节点 {node_name}] 输入数据类型不支持: {type(input_text)}, "
                    f"期望 str 或 List[str]，实际值: {input_text}"
                )
                logger.error(error_msg)
                raise TypeError(error_msg)
            
            # 调用 embedding 执行器
            # API 调用失败：抛出异常，中断流程执行
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
            
            # 处理输出：如果输入是单个字符串，返回单个向量；否则返回向量列表
            if isinstance(input_text, str):
                embedding_value = embeddings[0] if embeddings else []
            else:
                embedding_value = embeddings
            
            # 更新状态
            new_state = state.copy()
            
            # 关键：每次创建新 state 时，edges_var 使用新字典，不继承原始值
            # 确保上游节点的数据不会污染下游节点的条件判断
            new_state["edges_var"] = {}
            
            # 将结果保存到 edges_var
            new_state["edges_var"][output_field] = embedding_value
            
            logger.debug(
                f"[节点 {node_name}] 将 embedding 结果保存到 edges_var['{output_field}']"
            )
            
            return new_state
        
        return embedding_node_action
