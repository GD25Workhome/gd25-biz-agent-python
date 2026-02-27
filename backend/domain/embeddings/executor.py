"""
Embedding 执行器包装类
封装 Embedding 执行逻辑，提供统一的执行接口
"""
import logging
from typing import List

from backend.infrastructure.llm.embedding_client import EmbeddingClient

logger = logging.getLogger(__name__)


class EmbeddingExecutor:
    """Embedding 执行器包装类（兼容接口）"""
    
    def __init__(self, client: EmbeddingClient, verbose: bool = False):
        """
        初始化 Embedding 执行器
        
        Args:
            client: Embedding 客户端实例
            verbose: 是否输出详细信息
        """
        self.client = client
        self.verbose = verbose
    
    async def ainvoke(self, texts: List[str]) -> List[List[float]]:
        """
        异步调用 Embedding
        
        Args:
            texts: 文本列表
            
        Returns:
            List[List[float]]: 向量列表
        """
        if not texts:
            logger.warning("[EmbeddingExecutor] 输入文本列表为空")
            return []
        
        # 调用客户端进行 embedding
        embeddings = self.client.embed_documents(texts)
        
        if self.verbose:
            logger.debug(
                f"[EmbeddingExecutor] 成功生成 {len(embeddings)} 个向量，"
                f"向量维度: {len(embeddings[0]) if embeddings else 0}"
            )
        
        return embeddings
