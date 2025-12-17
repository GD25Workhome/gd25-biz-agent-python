"""
LLM 客户端封装
支持 DeepSeek API 和其他兼容 OpenAI 的 API
"""
from typing import Optional, List, Any
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from app.core.config import settings
from infrastructure.observability.llm_logger import (
    LlmLogCallbackHandler,
    LlmLogContext,
)


def get_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    log_context: Optional[LlmLogContext] = None,
    enable_logging: Optional[bool] = None,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 客户端实例（可选启用调用日志）
    
    Args:
        model: 模型名称，默认使用配置中的模型
        temperature: 温度参数，默认使用配置中的温度
        log_context: 日志上下文（用于链路追踪、用户/会话标记）
        enable_logging: 是否启用调用日志（默认读取配置）
        **kwargs: 其他参数（可以覆盖默认的 openai_api_key 和 base_url）
        
    Returns:
        BaseChatModel: LLM 客户端实例
    """
    # 解析温度与采样参数，允许外部覆盖
    resolved_temperature = temperature
    if resolved_temperature is None:
        resolved_temperature = settings.LLM_TEMPERATURE_DEFAULT
    if resolved_temperature is None:
        resolved_temperature = settings.LLM_TEMPERATURE
    
    resolved_top_p = kwargs.pop("top_p", settings.LLM_TOP_P_DEFAULT)
    resolved_max_tokens = kwargs.pop("max_tokens", settings.LLM_MAX_TOKENS_DEFAULT)
    
    log_enabled = enable_logging if enable_logging is not None else settings.LLM_LOG_ENABLE
    
    callbacks: List[Any] = list(kwargs.pop("callbacks", []) or [])
    if log_enabled:
        callbacks.append(
            LlmLogCallbackHandler(
                context=log_context,
                model=model or settings.LLM_MODEL,
                temperature=resolved_temperature,
                top_p=resolved_top_p,
                max_tokens=resolved_max_tokens,
                log_enabled=log_enabled,
            )
        )
    
    # 构建参数字典，kwargs 中的参数会覆盖默认值
    params = {
        "model": model or settings.LLM_MODEL,
        "temperature": resolved_temperature,
        "top_p": resolved_top_p,
        "max_tokens": resolved_max_tokens,
        "openai_api_key": settings.OPENAI_API_KEY,
        "base_url": settings.OPENAI_BASE_URL,
    }
    # kwargs 中的参数会覆盖默认值
    params.update(kwargs)
    
    if callbacks:
        params["callbacks"] = callbacks
    
    return ChatOpenAI(**params)

