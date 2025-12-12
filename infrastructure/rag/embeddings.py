import os
import logging
from typing import Union
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
from app.core.config import settings

logger = logging.getLogger(__name__)

def get_embeddings() -> Embeddings:
    """
    获取配置的 Embedding 模型。
    支持本地 HuggingFace 模型 (推荐) 和 OpenAI 兼容接口。
    
    Returns:
        Embeddings: LangChain Embeddings 接口实例
    """
    if settings.USE_LOCAL_EMBEDDING:
        # 设置 HF 镜像地址 (国内加速)
        os.environ['HF_ENDPOINT'] = settings.HF_ENDPOINT
        
        logger.info(f"正在加载本地 Embedding 模型: {settings.EMBEDDING_MODEL}")
        
        # 配置模型参数
        # 设备: 'cpu' 或 'cuda' 或 'mps' (Mac M1/M2)
        # 简单起见默认 cpu，生产环境可从配置读取
        model_kwargs = {'device': 'cpu'} 
        encode_kwargs = {'normalize_embeddings': True}
        
        return HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL,
            model_kwargs=model_kwargs,
            encode_kwargs=encode_kwargs
        )
    
    # 回退到 OpenAI/远程模式
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_BASE,
        dimensions=settings.EMBEDDING_DIMENSION
    )
