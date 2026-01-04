"""
LLM 客户端封装
支持多厂商、多模型的 LLM 客户端创建
"""
import logging
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from backend.infrastructure.llm.providers.manager import ProviderManager
from backend.infrastructure.llm.providers.registry import ProviderConfig
from backend.app.config import settings

logger = logging.getLogger(__name__)


def get_llm(
    provider: str,
    model: str,
    temperature: Optional[float] = None,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 客户端实例
    
    Args:
        provider: 模型供应商名称（如 "doubao", "openai", "deepseek"）
        model: 模型名称（如 "doubao-seed-1-6-251015"）
        temperature: 温度参数，默认使用配置中的温度
        **kwargs: 其他参数（可以覆盖默认的 api_key 和 base_url）
        
    Returns:
        BaseChatModel: LLM 客户端实例
        
    Raises:
        RuntimeError: 如果供应商配置未加载
        ValueError: 如果供应商不存在或配置无效
    """
    # 获取供应商配置
    provider_config = ProviderManager.get_provider(provider)
    if provider_config is None:
        raise ValueError(f"模型供应商 '{provider}' 未注册，请检查配置文件")
    
    # 使用传入的参数或供应商配置
    api_key = kwargs.get("api_key", provider_config.api_key)
    base_url = kwargs.get("base_url", provider_config.base_url)
    
    # 温度参数
    if temperature is None:
        temperature = settings.LLM_TEMPERATURE
    
    # 创建 LLM 客户端
    # 注意：所有供应商都使用 ChatOpenAI，因为它们都兼容 OpenAI API 格式
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=api_key,
        openai_api_base=base_url,
        **{k: v for k, v in kwargs.items() if k not in ["api_key", "base_url"]}
    )
    
    logger.debug(
        f"创建 LLM 客户端: provider={provider}, model={model}, "
        f"temperature={temperature}, base_url={base_url}"
    )
    
    return llm

