"""
Embedding 工厂
根据配置创建 Embedding 实例
"""
import logging
from typing import Optional

from backend.domain.embeddings.executor import EmbeddingExecutor
from backend.domain.flows.models.definition import EmbeddingNodeConfig, ModelConfig
from backend.infrastructure.llm.embedding_client import EmbeddingClient
from backend.infrastructure.llm.providers.manager import ProviderManager

logger = logging.getLogger(__name__)


class EmbeddingFactory:
    """Embedding 工厂"""
    
    @staticmethod
    def create_embedding_executor(
        config: EmbeddingNodeConfig
    ) -> EmbeddingExecutor:
        """
        创建 Embedding 执行器实例
        
        Args:
            config: Embedding 节点配置
            
        Returns:
            EmbeddingExecutor: Embedding 执行器
        """
        model_config = config.model
        
        # 创建 Embedding 客户端
        # 从 ProviderManager 获取供应商配置（配置来源：config/model_providers.yaml）
        provider_config = ProviderManager.get_provider(model_config.provider)
        if provider_config is None:
            raise ValueError(
                f"模型供应商 '{model_config.provider}' 未注册，"
                f"请检查 config/model_providers.yaml 配置文件"
            )
        
        # 创建 EmbeddingClient 实例
        embedding_client = EmbeddingClient(
            provider=model_config.provider,
            model=model_config.name,
            api_key=provider_config.api_key
        )
        
        logger.debug(
            f"创建 Embedding 执行器: provider={model_config.provider}, "
            f"model={model_config.name}"
        )
        
        return EmbeddingExecutor(embedding_client, verbose=True)
