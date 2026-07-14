"""
AutoGen 模型客户端桥接

将 ProviderManager 配置转换为 AutoGen OpenAIChatCompletionClient。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from autogen_ext.models.openai import OpenAIChatCompletionClient

from backend.infrastructure.llm.providers.manager import ProviderManager

logger = logging.getLogger(__name__)

# 非 OpenAI 官方模型名时必须显式声明能力（如豆包 ARK）
_DEFAULT_MODEL_INFO: dict[str, Any] = {
    "vision": False,
    "function_calling": True,
    "json_output": True,
    "family": "unknown",
    "structured_output": True,
}


def get_autogen_model_client(
    provider: str,
    model: str,
    temperature: float = 0.7,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """
        从 ProviderManager 读取供应商配置，构造 AutoGen OpenAI 兼容客户端。

        与 get_llm 的差异：返回 AutoGen client；不注入 LangChain Callback；
        首期不传豆包 thinking / reasoning_effort。

        Args:
            provider: 供应商名称（如 doubao）
            model: 模型名称
            temperature: 温度
            api_key: 可选覆盖 api_key
            base_url: 可选覆盖 base_url

        Returns:
            OpenAIChatCompletionClient 实例

        Raises:
            ValueError: 供应商未注册或配置无效
    """
    # 1. 确保供应商配置已加载
    if not ProviderManager.is_loaded():
        ProviderManager.load_providers()

    # 2. 读取并校验供应商
    provider_config = ProviderManager.get_provider(provider)
    if provider_config is None:
        raise ValueError(f"模型供应商 '{provider}' 未注册，请检查配置文件")

    resolved_api_key = api_key if api_key is not None else provider_config.api_key
    resolved_base_url = base_url if base_url is not None else provider_config.base_url

    if not resolved_api_key:
        raise ValueError(f"模型供应商 '{provider}' 缺少 api_key")
    if not resolved_base_url:
        raise ValueError(f"模型供应商 '{provider}' 缺少 base_url")

    # 3. 构造 AutoGen client（非 OpenAI 模型名需带 model_info）
    client = OpenAIChatCompletionClient(
        model=model,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        temperature=temperature,
        model_info=_DEFAULT_MODEL_INFO,
    )
    logger.debug(
        "创建 AutoGen model client: provider=%s, model=%s, base_url=%s",
        provider,
        model,
        resolved_base_url,
    )
    return client
