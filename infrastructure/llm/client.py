"""
LLM 客户端封装
支持 DeepSeek API 和其他兼容 OpenAI 的 API
"""
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from app.core.config import settings


def get_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 客户端实例
    
    Args:
        model: 模型名称，默认使用配置中的模型
        temperature: 温度参数，默认使用配置中的温度
        **kwargs: 其他参数（可以覆盖默认的 openai_api_key 和 base_url）
        
    Returns:
        BaseChatModel: LLM 客户端实例
    """
    # 构建参数字典，kwargs 中的参数会覆盖默认值
    params = {
        "model": model or settings.LLM_MODEL,
        "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
        "openai_api_key": settings.OPENAI_API_KEY,
        "base_url": settings.OPENAI_BASE_URL,
    }
    # kwargs 中的参数会覆盖默认值
    params.update(kwargs)
    
    return ChatOpenAI(**params)

