"""
LLM 客户端封装（简化版）
支持多厂商、多模型的 LLM 客户端创建
集成Langfuse可观测性
"""
import logging
from typing import Optional, List
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from langchain_core.callbacks import BaseCallbackHandler

from .providers.manager import ProviderManager
from core.config import settings
from langfuse_local.handler import create_langfuse_handler

logger = logging.getLogger(__name__)


def get_llm(
    provider: str,
    model: str,
    temperature: Optional[float] = None,
    callbacks: Optional[List[BaseCallbackHandler]] = None,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 客户端实例
    
    Args:
        provider: 模型供应商名称（如 "doubao", "openai", "deepseek"）
        model: 模型名称（如 "doubao-seed-1-6-251015"）
        temperature: 温度参数，默认使用配置中的温度
        callbacks: 回调处理器列表（可选，如果未提供则自动添加Langfuse回调）
        **kwargs: 其他参数（可以覆盖默认的 api_key 和 base_url）
        
    Returns:
        BaseChatModel: LLM 客户端实例
        
    Raises:
        ValueError: 如果供应商不存在或配置无效
    """
    # 获取供应商配置
    provider_config = ProviderManager.get_provider(provider)
    if provider_config is None:
        raise ValueError(f"模型供应商 '{provider}' 未注册，请检查配置")
    
    # 使用传入的参数或供应商配置
    api_key = kwargs.get("api_key", provider_config.api_key)
    base_url = kwargs.get("base_url", provider_config.base_url)
    
    # 温度参数
    if temperature is None:
        temperature = settings.LLM_TEMPERATURE
    
    # 准备回调处理器列表
    callback_list = list(callbacks) if callbacks else []
    
    # 自动添加Langfuse回调处理器（如果可用且未手动提供）
    if not callbacks:
        langfuse_handler = create_langfuse_handler(
            context={
                "provider": provider,
                "model": model,
                "temperature": temperature,
            }
        )
        if langfuse_handler:
            callback_list.append(langfuse_handler)
            logger.info(
                f"[Langfuse] 自动添加CallbackHandler: provider={provider}, "
                f"model={model}, callbacks_count={len(callback_list)}"
            )
        else:
            logger.debug(
                f"[Langfuse] CallbackHandler不可用，跳过: provider={provider}, model={model}"
            )
    
    # 创建 LLM 客户端
    # 注意：所有供应商都使用 ChatOpenAI，因为它们都兼容 OpenAI API 格式
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=api_key,
        openai_api_base=base_url,
        callbacks=callback_list if callback_list else None,
        **{k: v for k, v in kwargs.items() if k not in ["api_key", "base_url"]}
    )
    
    logger.debug(
        f"创建 LLM 客户端: provider={provider}, model={model}, "
        f"temperature={temperature}, base_url={base_url}, "
        f"callbacks_count={len(callback_list)}"
    )
    
    return llm

