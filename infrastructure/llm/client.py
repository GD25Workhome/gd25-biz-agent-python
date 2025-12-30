"""
LLM 客户端封装
支持 DeepSeek API 和其他兼容 OpenAI 的 API
"""
import logging
from typing import Optional, List, Any

# 应用 reasoning_content 提取补丁（必须在导入 ChatOpenAI 之前）
from infrastructure.llm.reasoning_patch import apply_reasoning_patch

# 应用补丁（只执行一次）
_patch_applied = False
if not _patch_applied:
    apply_reasoning_patch()
    _patch_applied = True

from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from app.core.config import settings
from infrastructure.observability.llm_logger import (
    LlmLogCallbackHandler,
    LlmLogContext,
)

logger = logging.getLogger(__name__)


def get_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    log_context: Optional[LlmLogContext] = None,
    enable_logging: Optional[bool] = None,
    enable_langfuse: Optional[bool] = None,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 客户端实例（可选启用调用日志和 Langfuse 追踪）
    
    Args:
        model: 模型名称，默认使用配置中的模型
        temperature: 温度参数，默认使用配置中的温度
        log_context: 日志上下文（用于链路追踪、用户/会话标记）
        enable_logging: 是否启用调用日志（默认读取配置）
        enable_langfuse: 是否启用 Langfuse 追踪（默认读取配置）
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
    # 移除 max_tokens 限制，使用 API 默认行为（无限制）
    
    log_enabled = enable_logging if enable_logging is not None else settings.LLM_LOG_ENABLE
    langfuse_enabled = enable_langfuse if enable_langfuse is not None else settings.LANGFUSE_ENABLED
    
    callbacks: List[Any] = list(kwargs.pop("callbacks", []) or [])
    
    # 添加 Langfuse Callback（如果启用）
    if langfuse_enabled:
        try:
            from infrastructure.observability.langfuse_handler import create_langfuse_handler
            langfuse_handler = create_langfuse_handler(log_context)
            callbacks.append(langfuse_handler)
            logger.debug("已添加Langfuse Callback Handler")
        except (ImportError, ValueError) as e:
            # Langfuse未安装或未启用，记录警告但不影响主流程
            logger.warning(f"创建Langfuse handler失败: {e}，继续执行但不记录到Langfuse")
        except Exception as e:
            # 其他异常，记录错误但不影响主流程
            logger.error(f"创建Langfuse handler时发生异常: {e}，继续执行但不记录到Langfuse", exc_info=True)
    
    # 总是添加日志回调处理器，用于控制台日志输出
    # 数据库日志写入由 log_enabled 参数控制
    callbacks.append(
        LlmLogCallbackHandler(
            context=log_context,
            model=model or settings.LLM_MODEL,
            temperature=resolved_temperature,
            top_p=resolved_top_p,
            max_tokens=None,  # 不限制 max_tokens，使用 API 默认行为
            log_enabled=log_enabled,  # 控制数据库日志，但不影响控制台日志
        )
    )
    
    # 检查关键配置
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY 未配置，请设置 OPENAI_API_KEY")
    if not settings.OPENAI_BASE_URL:
        raise ValueError("OPENAI_BASE_URL 未配置，请设置 OPENAI_BASE_URL")
    if not settings.LLM_MODEL and not model:
        raise ValueError("LLM_MODEL 未配置，请设置 LLM_MODEL 或传入 model 参数")
    
    # 构建参数字典，kwargs 中的参数会覆盖默认值
    # 注意：不设置 max_tokens，使用 API 默认行为（无限制）
    params = {
        "model": model or settings.LLM_MODEL,
        "temperature": resolved_temperature,
        "top_p": resolved_top_p,
        "openai_api_key": settings.OPENAI_API_KEY,
        "base_url": settings.OPENAI_BASE_URL,
    }
    # kwargs 中的参数会覆盖默认值
    # 如果 kwargs 中包含 max_tokens，也会被移除（不设置限制）
    kwargs.pop("max_tokens", None)
    params.update(kwargs)
    
    if callbacks:
        params["callbacks"] = callbacks
    
    return ChatOpenAI(**params)

