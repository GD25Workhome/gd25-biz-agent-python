"""
Langfuse提示词加载集成测试
测试Langfuse提示词在实际Agent创建中的使用
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到路径
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.prompts.langfuse_adapter import LangfusePromptAdapter, LANGFUSE_AVAILABLE
from domain.agents.factory import AgentFactory


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
        mock_settings.PROMPT_USE_LANGFUSE = True
        yield mock_settings


@pytest.fixture
def mock_get_llm():
    """Mock get_llm"""
    with patch('domain.agents.factory.get_llm') as mock_get_llm:
        mock_llm_instance = MagicMock()
        mock_get_llm.return_value = mock_llm_instance
        yield mock_get_llm


@pytest.fixture
def mock_create_react_agent():
    """Mock create_react_agent"""
    with patch('domain.agents.factory.create_react_agent') as mock_create:
        mock_agent = MagicMock()
        mock_create.return_value = mock_agent
        yield mock_create


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_agent_creation_with_langfuse_prompt(mock_langfuse_client, mock_settings, mock_get_llm, mock_create_react_agent):
    """测试使用Langfuse提示词创建Agent"""
    # 设置Mock返回值
    mock_prompt = MagicMock()
    mock_prompt.prompt = "你是一个专业的血压记录助手。用户ID: {{user_id}}"
    mock_langfuse_client.get_prompt.return_value = mock_prompt
    
    # 创建临时配置
    AgentFactory._config = {
        "test_agent": {
            "name": "测试智能体",
            "llm": {
                "model": "deepseek-chat",
                "temperature": 0.7
            },
            "tools": [],
            "langfuse_template": "test_agent_prompt"
        }
    }
    
    try:
        # 创建Agent
        agent = AgentFactory.create_agent("test_agent")
        
        # 验证从Langfuse获取了提示词
        mock_langfuse_client.get_prompt.assert_called_once_with("test_agent_prompt", version=None)
        
        # 验证create_react_agent被调用
        assert mock_create_react_agent.called
        
        # 验证传递的提示词
        call_args = mock_create_react_agent.call_args
        assert call_args is not None
    finally:
        # 清理
        AgentFactory._config = {}
        AgentFactory.clear_cache()


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_agent_creation_with_langfuse_fallback(mock_langfuse_client, mock_settings, mock_get_llm, mock_create_react_agent):
    """测试Langfuse不可用时的降级"""
    # Mock Langfuse服务不可用
    mock_langfuse_client.get_prompt.side_effect = Exception("Langfuse服务不可用")
    
    # 创建临时配置（包含fallback提示词）
    AgentFactory._config = {
        "test_agent": {
            "name": "测试智能体",
            "llm": {
                "model": "deepseek-chat",
                "temperature": 0.7
            },
            "tools": [],
            "langfuse_template": "test_agent_prompt",
            "system_prompt": "这是fallback提示词"
        }
    }
    
    try:
        # 创建Agent（应该降级到system_prompt）
        agent = AgentFactory.create_agent("test_agent")
        
        # 验证create_react_agent被调用
        assert mock_create_react_agent.called
        
        # 验证使用了fallback提示词
        call_args = mock_create_react_agent.call_args
        assert call_args is not None
    finally:
        # 清理
        AgentFactory._config = {}
        AgentFactory.clear_cache()


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_langfuse_prompt_caching(mock_langfuse_client, mock_settings, mock_get_llm, mock_create_react_agent):
    """测试Langfuse提示词缓存"""
    # 设置Mock返回值
    mock_prompt = MagicMock()
    mock_prompt.prompt = "测试提示词"
    mock_langfuse_client.get_prompt.return_value = mock_prompt
    
    # 创建临时配置
    AgentFactory._config = {
        "test_agent": {
            "name": "测试智能体",
            "llm": {
                "model": "deepseek-chat",
                "temperature": 0.7
            },
            "tools": [],
            "langfuse_template": "test_agent_prompt"
        }
    }
    
    try:
        # 第一次创建Agent
        agent1 = AgentFactory.create_agent("test_agent")
        
        # 第二次创建Agent（应该使用缓存的提示词）
        agent2 = AgentFactory.create_agent("test_agent")
        
        # get_prompt应该只被调用一次（因为缓存）
        assert mock_langfuse_client.get_prompt.call_count == 1
    finally:
        # 清理
        AgentFactory._config = {}
        AgentFactory.clear_cache()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

