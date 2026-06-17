"""
LLM 客户端工厂

根据 provider 名称与 flow.yaml 中的 model 配置，创建 LangChain BaseChatModel 实例。
豆包在需要 thinking / reasoning_effort 时使用 DoubaoChatOpenAI 包装类；其余走 ChatOpenAI 兼容接口。
Langfuse 回调由外层 LangGraph config 注入，本模块不在此层挂载 callbacks。
"""
import logging
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.app.config import settings
from backend.infrastructure.llm.providers.manager import ProviderManager

logger = logging.getLogger(__name__)


def get_llm(
    provider: str,
    model: str,
    temperature: Optional[float] = None,
    thinking: Optional[Dict[str, str]] = None,
    reasoning_effort: Optional[str] = None,
    timeout: Optional[int] = None,
    **kwargs: Any,
) -> BaseChatModel:
    """
        按供应商配置创建 LLM 客户端（AgentFactory、Embedding 等调用入口）。

        Args:
            provider: 供应商名称，与 model_providers.yaml 中 key 一致（如 doubao）
            model: 模型名（如 doubao-seed-1-6-251015）
            temperature: 采样温度；None 时使用 settings.LLM_TEMPERATURE
            thinking: 豆包思考模式，如 {"type": "enabled"} / {"type": "disabled"}
            reasoning_effort: 豆包推理力度 minimal/low/medium/high
            timeout: 请求超时秒数；None 且 thinking.enabled 时默认 1800
            **kwargs: 可覆盖 api_key、base_url 等 ChatOpenAI 构造参数

        Returns:
            BaseChatModel: 可直接传入 langchain create_agent 的聊天模型

        Raises:
            ValueError: provider 未在 ProviderManager 中注册
    """
    # 1. 读取供应商 api_key / base_url
    provider_config = ProviderManager.get_provider(provider)
    if provider_config is None:
        raise ValueError(f"模型供应商 '{provider}' 未注册，请检查配置文件")

    api_key = kwargs.get("api_key", provider_config.api_key)
    base_url = kwargs.get("base_url", provider_config.base_url)
    extra_kwargs = {k: v for k, v in kwargs.items() if k not in ["api_key", "base_url"]}

    # 2. 填充默认 temperature 与 timeout
    if temperature is None:
        temperature = settings.LLM_TEMPERATURE
    if timeout is None:
        timeout = 1800 if thinking and thinking.get("type") == "enabled" else None

    # 3. 豆包 + thinking/reasoning 参数：使用 DoubaoChatOpenAI 注入厂商扩展字段
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
            **extra_kwargs,
        )
        logger.debug(
            f"创建豆包 LLM 包装类: provider={provider}, model={model}, "
            f"thinking={thinking}, reasoning_effort={reasoning_effort}, timeout={timeout}"
        )
        return llm

    # 4. 默认路径：OpenAI 兼容 ChatOpenAI
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=api_key,
        openai_api_base=base_url,
        timeout=timeout,
        **extra_kwargs,
    )
    logger.debug(
        f"创建 LLM 客户端: provider={provider}, model={model}, "
        f"temperature={temperature}, base_url={base_url}"
    )
    return llm
