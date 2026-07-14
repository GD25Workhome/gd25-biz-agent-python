"""
AutoGen 模型客户端桥接测试
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.infrastructure.llm.autogen_client import get_autogen_model_client


def test_get_autogen_model_client_uses_provider_config() -> None:
    """应从 ProviderManager 读取 base_url / api_key 并传给 OpenAIChatCompletionClient。"""
    fake_provider = SimpleNamespace(
        api_key="sk-test",
        base_url="https://ark.example.com/api/v3",
        default_model="doubao-test",
    )

    with (
        patch(
            "backend.infrastructure.llm.autogen_client.ProviderManager.is_loaded",
            return_value=True,
        ),
        patch(
            "backend.infrastructure.llm.autogen_client.ProviderManager.get_provider",
            return_value=fake_provider,
        ),
        patch(
            "backend.infrastructure.llm.autogen_client.OpenAIChatCompletionClient"
        ) as mock_client_cls,
    ):
        mock_client_cls.return_value = MagicMock()
        client = get_autogen_model_client(
            provider="doubao",
            model="doubao-seed-1-8-251228",
            temperature=0.3,
        )

        assert client is mock_client_cls.return_value
        kwargs = mock_client_cls.call_args.kwargs
        assert kwargs["model"] == "doubao-seed-1-8-251228"
        assert kwargs["api_key"] == "sk-test"
        assert kwargs["base_url"] == "https://ark.example.com/api/v3"
        assert kwargs["temperature"] == 0.3
        assert "model_info" in kwargs


def test_get_autogen_model_client_unknown_provider() -> None:
    """未知供应商应抛出 ValueError。"""
    with (
        patch(
            "backend.infrastructure.llm.autogen_client.ProviderManager.is_loaded",
            return_value=True,
        ),
        patch(
            "backend.infrastructure.llm.autogen_client.ProviderManager.get_provider",
            return_value=None,
        ),
    ):
        with pytest.raises(ValueError, match="未注册"):
            get_autogen_model_client(provider="no-such", model="x")
