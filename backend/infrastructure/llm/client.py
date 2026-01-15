"""
LLM 客户端封装
支持多厂商、多模型的 LLM 客户端创建
集成Langfuse可观测性
"""
import logging
from typing import Optional, List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from langchain_core.callbacks import BaseCallbackHandler

from backend.infrastructure.llm.providers.manager import ProviderManager
from backend.infrastructure.llm.providers.registry import ProviderConfig
from backend.app.config import settings
from backend.infrastructure.observability.langfuse_handler import create_langfuse_handler

logger = logging.getLogger(__name__)


def get_llm(
    provider: str,
    model: str,
    temperature: Optional[float] = None,
    thinking: Optional[Dict[str, str]] = None,
    reasoning_effort: Optional[str] = None,
    timeout: Optional[int] = None,
    # callbacks: Optional[List[BaseCallbackHandler]] = None,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 客户端实例
    
    Args:
        provider: 模型供应商名称（如 "doubao", "openai", "deepseek"）
        model: 模型名称（如 "doubao-seed-1-6-251015"）
        temperature: 温度参数，默认使用配置中的温度
        thinking: 思考模式配置
        reasoning_effort: 推理努力程度
        timeout: 超时时间（秒）
        callbacks: 回调处理器列表（可选，如果未提供则自动添加Langfuse回调）
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
    
    # 超时参数（深度思考时建议设置为 1800 秒）
    if timeout is None:
        timeout = 1800 if thinking and thinking.get("type") == "enabled" else None
    
    # 如果是豆包供应商且设置了 thinking 或 reasoning_effort，使用包装类
    if provider == "doubao" and (thinking is not None or reasoning_effort is not None):
        from backend.infrastructure.llm.doubao_chat import DoubaoChatOpenAI
        llm = DoubaoChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=api_key,
            openai_api_base=base_url,
            timeout=timeout,
            thinking=thinking,
            reasoning_effort=reasoning_effort,
            **{k: v for k, v in kwargs.items() if k not in ["api_key", "base_url"]}
        )
        logger.debug(
            f"创建豆包 LLM 包装类: provider={provider}, model={model}, "
            f"thinking={thinking}, reasoning_effort={reasoning_effort}, timeout={timeout}"
        )
    else:
        # 创建普通 ChatOpenAI 实例
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=api_key,
            openai_api_base=base_url,
            timeout=timeout,
            # callbacks=callbacks if callbacks else None,
            **{k: v for k, v in kwargs.items() if k not in ["api_key", "base_url"]}
        )
        logger.debug(
            f"创建 LLM 客户端: provider={provider}, model={model}, "
            f"temperature={temperature}, base_url={base_url}"
        )
    
    return llm

