"""
Langfuse Prompt Adapter 单元测试
"""
import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# 添加项目根目录到路径
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.prompts.langfuse_adapter import LangfusePromptAdapter, LANGFUSE_AVAILABLE
from app.core.config import settings


@pytest.fixture
def mock_langfuse_client():
    """Mock Langfuse客户端"""
    with patch('infrastructure.prompts.langfuse_adapter.Langfuse') as mock_langfuse:
        mock_client = MagicMock()
        mock_langfuse.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_settings():
    """Mock设置"""
    with patch('infrastructure.prompts.langfuse_adapter.settings') as mock_settings:
        mock_settings.LANGFUSE_ENABLED = True
        mock_settings.LANGFUSE_PUBLIC_KEY = "pk-test"
        mock_settings.LANGFUSE_SECRET_KEY = "sk-test"
        mock_settings.LANGFUSE_HOST = "https://cloud.langfuse.com"
        mock_settings.PROMPT_CACHE_TTL = 300
        yield mock_settings


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_get_template_from_langfuse(mock_langfuse_client, mock_settings):
    """测试从Langfuse获取模版"""
    # 设置Mock返回值
    mock_prompt = MagicMock()
    mock_prompt.prompt = "这是一个测试模版"
    mock_langfuse_client.get_prompt.return_value = mock_prompt
    
    adapter = LangfusePromptAdapter()
    template = adapter.get_template("test_template")
    
    assert template == "这是一个测试模版"
    mock_langfuse_client.get_prompt.assert_called_once_with("test_template", version=None)


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_template_caching(mock_langfuse_client, mock_settings):
    """测试模版缓存机制"""
    # 设置Mock返回值
    mock_prompt = MagicMock()
    mock_prompt.prompt = "缓存的模版"
    mock_langfuse_client.get_prompt.return_value = mock_prompt
    
    adapter = LangfusePromptAdapter()
    
    # 第一次获取
    template1 = adapter.get_template("test_template")
    assert template1 == "缓存的模版"
    
    # 第二次获取（应该使用缓存）
    template2 = adapter.get_template("test_template")
    assert template2 == "缓存的模版"
    
    # 应该只调用一次get_prompt
    assert mock_langfuse_client.get_prompt.call_count == 1


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_fallback_to_local(mock_langfuse_client, mock_settings):
    """测试Langfuse不可用时的降级"""
    # Mock Langfuse服务不可用
    mock_langfuse_client.get_prompt.side_effect = Exception("Langfuse服务不可用")
    
    # 创建临时测试文件
    test_file = project_root / "config" / "prompts" / "test_template.txt"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("本地降级模版", encoding="utf-8")
    
    try:
        adapter = LangfusePromptAdapter()
        template = adapter.get_template("test_template", fallback_to_local=True)
        
        assert template == "本地降级模版"
    finally:
        # 清理测试文件
        if test_file.exists():
            test_file.unlink()


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_clear_cache(mock_langfuse_client, mock_settings):
    """测试清除缓存"""
    mock_prompt = MagicMock()
    mock_prompt.prompt = "测试模版"
    mock_langfuse_client.get_prompt.return_value = mock_prompt
    
    adapter = LangfusePromptAdapter()
    
    # 获取模版（会缓存）
    adapter.get_template("test_template")
    assert len(adapter._cache) == 1
    
    # 清除缓存
    adapter.clear_cache("test_template")
    assert len(adapter._cache) == 0


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_is_available(mock_langfuse_client, mock_settings):
    """测试检查Langfuse是否可用"""
    adapter = LangfusePromptAdapter()
    assert adapter.is_available() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

