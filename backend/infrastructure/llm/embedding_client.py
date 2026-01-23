"""
Embedding 客户端封装（基础设施层）
负责底层 API 调用，不包含业务逻辑
"""
import logging
from typing import List, Optional
from volcenginesdkarkruntime import Ark

from backend.infrastructure.llm.providers.manager import ProviderManager

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Embedding 客户端封装"""
    
    def __init__(self, provider: str, model: str, api_key: Optional[str] = None):
        """
        初始化 Embedding 客户端
        
        Args:
            provider: 模型供应商名称（如 "doubao-embedding"）
            model: 模型名称（如 "doubao-embedding-vision-250615"）
            api_key: API 密钥（可选，默认从 ProviderManager 读取配置）
        
        注意：
            - 配置来源：通过 ProviderManager 从 config/model_providers.yaml 读取
            - 不会直接从环境变量读取，必须通过 ProviderManager 统一管理
            - 确保应用启动时已调用 ProviderManager.load_providers()
        """
        self.provider = provider
        self.model = model
        
        # 从 ProviderManager 获取供应商配置（配置来源：config/model_providers.yaml）
        # 重要：必须通过 ProviderManager 获取，不要直接从环境变量读取
        provider_config = ProviderManager.get_provider(provider)
        if provider_config is None:
            raise ValueError(
                f"模型供应商 '{provider}' 未注册，请检查 config/model_providers.yaml 配置文件"
            )
        
        # 使用传入的 api_key 或从 ProviderManager 配置读取
        # provider_config.api_key 已经从 model_providers.yaml 解析环境变量占位符
        self.api_key = api_key or provider_config.api_key
        if not self.api_key:
            raise ValueError(
                f"供应商 {provider} 的 API 密钥未设置，"
                f"请检查 config/model_providers.yaml 中的配置和环境变量"
            )
        
        # 创建客户端
        self.client = Ark(api_key=self.api_key)
        logger.debug(f"创建 Embedding 客户端: provider={provider}, model={model}")
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        批量嵌入文档
        
        注意：豆包 API 在批量调用时可能返回单个合并的向量，因此需要逐个调用以确保每个文本都有独立的向量。
        
        Args:
            texts: 文本列表
            
        Returns:
            List[List[float]]: 向量列表
        """
        if not texts:
            return []
        
        # 豆包 API 在批量调用时返回单个合并向量，因此需要逐个调用
        # 以确保每个文本都有独立的向量
        embeddings = []
        for text in texts:
            # 转换为豆包 API 格式
            input_data = [{"type": "text", "text": text}]
            
            # 调用 API
            resp = self.client.multimodal_embeddings.create(
                model=self.model,
                input=input_data
            )
            
            # 解析响应
            if hasattr(resp, 'data') and hasattr(resp.data, 'embedding'):
                embedding = resp.data.embedding
                if isinstance(embedding, list):
                    # 如果是嵌套列表（多个向量），取第一个
                    if embedding and isinstance(embedding[0], list):
                        embeddings.append(embedding[0])
                    else:
                        # 单个向量，直接添加
                        embeddings.append(embedding)
        
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """
        嵌入单个查询文本
        
        Args:
            text: 查询文本
            
        Returns:
            List[float]: 向量
        """
        results = self.embed_documents([text])
        return results[0] if results else []
