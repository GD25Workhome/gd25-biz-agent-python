"""
LangfuseLoader 单元测试
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到路径
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.prompts.langfuse_loader import LangfuseLoader
from infrastructure.prompts.langfuse_adapter import LangfusePromptAdapter, LANGFUSE_AVAILABLE


@pytest.fixture
def mock_adapter():
    """Mock Langfuse适配器"""
    adapter = MagicMock(spec=LangfusePromptAdapter)
    adapter.get_template.return_value = "测试模版内容"
    adapter.is_available.return_value = True
    return adapter


@pytest.fixture
def mock_settings():
    """Mock设置（用于LangfusePromptAdapter初始化）"""
    # 注意：settings 在 langfuse_adapter.py 中导入，不在 langfuse_loader.py 中
    with patch('infrastructure.prompts.langfuse_adapter.settings') as mock_settings:
        mock_settings.LANGFUSE_ENABLED = True
        mock_settings.PROMPT_USE_LANGFUSE = True
        mock_settings.LANGFUSE_PUBLIC_KEY = "pk-test"
        mock_settings.LANGFUSE_SECRET_KEY = "sk-test"
        mock_settings.LANGFUSE_HOST = "https://cloud.langfuse.com"
        mock_settings.PROMPT_CACHE_TTL = 300
        yield mock_settings


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_load_template(mock_adapter):
    """测试从Langfuse加载模版"""
    loader = LangfuseLoader(adapter=mock_adapter)
    
    template = loader.load("test_template")
    
    assert template == "测试模版内容"
    mock_adapter.get_template.assert_called_once_with(
        template_name="test_template",
        version=None,
        fallback_to_local=True
    )


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_load_template_with_version(mock_adapter):
    """测试从Langfuse加载指定版本的模版"""
    loader = LangfuseLoader(adapter=mock_adapter)
    
    context = {"version": "v1.0"}
    template = loader.load("test_template", context=context)
    
    assert template == "测试模版内容"
    mock_adapter.get_template.assert_called_once_with(
        template_name="test_template",
        version="v1.0",
        fallback_to_local=True
    )


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_load_template_with_placeholders(mock_adapter):
    """测试加载模版并填充占位符"""
    mock_adapter.get_template.return_value = "用户ID: {{user_id}}, 会话ID: {{session_id}}"
    loader = LangfuseLoader(adapter=mock_adapter)
    
    context = {
        "user_id": "user_123",
        "session_id": "session_456"
    }
    template = loader.load("test_template", context=context)
    
    assert "user_123" in template
    assert "session_456" in template
    assert "{{user_id}}" not in template
    assert "{{session_id}}" not in template


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_supports_langfuse_protocol(mock_adapter):
    """测试支持langfuse://协议"""
    loader = LangfuseLoader(adapter=mock_adapter)
    
    assert loader.supports("langfuse://test_template") is True


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_supports_template_name(mock_adapter):
    """测试支持模版名称"""
    loader = LangfuseLoader(adapter=mock_adapter)
    
    # 模版名称（不包含路径分隔符）
    assert loader.supports("test_template") is True
    # 包含路径分隔符的应该不支持
    assert loader.supports("config/prompts/test.txt") is False


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_adapter_lazy_initialization(mock_settings):
    """测试适配器延迟初始化"""
    with patch('infrastructure.prompts.langfuse_loader.LangfusePromptAdapter') as mock_adapter_class:
        mock_adapter_instance = MagicMock()
        mock_adapter_instance.get_template.return_value = "测试模版"
        mock_adapter_instance.is_available.return_value = True
        mock_adapter_class.return_value = mock_adapter_instance
        
        loader = LangfuseLoader()
        
        # 第一次访问adapter属性时应该创建适配器
        template = loader.load("test_template")
        
        assert template == "测试模版"
        mock_adapter_class.assert_called_once()


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_adapter_unavailable(mock_settings):
    """测试适配器不可用的情况"""
    with patch('infrastructure.prompts.langfuse_loader.LangfusePromptAdapter') as mock_adapter_class:
        mock_adapter_class.side_effect = ValueError("Langfuse未启用")
        
        loader = LangfuseLoader()
        
        # adapter属性应该为None
        assert loader.adapter is None
        
        # 尝试加载应该抛出异常
        with pytest.raises(ValueError, match="Langfuse适配器不可用"):
            loader.load("test_template")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

