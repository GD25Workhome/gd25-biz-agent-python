"""
LLM 配置与日志回调单元测试
"""
from typing import Any

import pytest

from infrastructure.llm import client
from infrastructure.llm.client import get_llm
from infrastructure.observability.llm_logger import LlmLogCallbackHandler
from app.core.config import settings


class _DummyLLM:
    """用于拦截 ChatOpenAI 初始化参数的哑对象"""
    
    def __init__(self, **kwargs: Any):
        self.kwargs = kwargs
    
    # 兼容调用
    def invoke(self, *_args, **_kwargs):
        return None


def test_get_llm_uses_env_temperature(monkeypatch: pytest.MonkeyPatch):
    """验证 get_llm 使用可配置温度并附加日志回调"""
    monkeypatch.setattr(client, "ChatOpenAI", _DummyLLM)
    monkeypatch.setattr(settings, "LLM_TEMPERATURE_DEFAULT", 0.55)
    monkeypatch.setattr(settings, "LLM_LOG_ENABLE", True)
    
    llm = get_llm()
    
    assert isinstance(llm, _DummyLLM)
    assert llm.kwargs["temperature"] == 0.55
    callbacks = llm.kwargs.get("callbacks") or []
    assert any(isinstance(cb, LlmLogCallbackHandler) for cb in callbacks)


def test_get_llm_disable_logging(monkeypatch: pytest.MonkeyPatch):
    """验证禁用日志时不会注入回调"""
    monkeypatch.setattr(client, "ChatOpenAI", _DummyLLM)
    monkeypatch.setattr(settings, "LLM_TEMPERATURE_DEFAULT", 0.1)
    monkeypatch.setattr(settings, "LLM_LOG_ENABLE", False)
    
    llm = get_llm()
    
    assert isinstance(llm, _DummyLLM)
    assert llm.kwargs["temperature"] == 0.1
    assert "callbacks" not in llm.kwargs
