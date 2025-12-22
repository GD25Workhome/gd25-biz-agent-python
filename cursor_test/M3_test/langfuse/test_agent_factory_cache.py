"""
AgentFactory 缓存和热更新功能单元测试
"""
import pytest
import os
import tempfile
import yaml
import time
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# 添加项目根目录到路径
import sys
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from domain.agents.factory import AgentFactory


@pytest.fixture
def temp_config_file():
    """创建临时配置文件"""
    config = {
        "agents": {
            "test_agent": {
                "name": "测试智能体",
                "llm": {
                    "model": "deepseek-chat",
                    "temperature": 0.7
                },
                "tools": [],
                "system_prompt": "你是一个测试助手"
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f, allow_unicode=True)
        config_path = f.name
    
    yield config_path
    
    # 清理
    if os.path.exists(config_path):
        os.unlink(config_path)
    # 清除缓存
    AgentFactory.clear_cache()
    AgentFactory._config = {}
    AgentFactory._config_path = "config/agents.yaml"
    AgentFactory._config_mtime = None


@pytest.fixture
def mock_llm():
    """Mock LLM实例"""
    with patch('domain.agents.factory.get_llm') as mock_get_llm:
        mock_llm_instance = MagicMock()
        mock_get_llm.return_value = mock_llm_instance
        yield mock_llm_instance


@pytest.fixture
def mock_create_react_agent():
    """Mock create_react_agent"""
    with patch('domain.agents.factory.create_react_agent') as mock_create:
        mock_agent = MagicMock()  # 不指定spec，避免导入问题
        mock_create.return_value = mock_agent
        yield mock_create


def test_agent_caching(temp_config_file, mock_llm, mock_create_react_agent):
    """测试Agent缓存机制"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    
    # 第一次创建Agent
    agent1 = AgentFactory.create_agent("test_agent")
    
    # 第二次创建Agent（应该使用缓存）
    agent2 = AgentFactory.create_agent("test_agent")
    
    # 应该是同一个实例
    assert agent1 is agent2
    
    # create_react_agent应该只被调用一次
    assert mock_create_react_agent.call_count == 1


def test_force_reload(temp_config_file, mock_llm, mock_create_react_agent):
    """测试强制重新加载"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    
    # 第一次创建Agent
    agent1 = AgentFactory.create_agent("test_agent")
    
    # 强制重新加载
    agent2 = AgentFactory.create_agent("test_agent", force_reload=True)
    
    # 应该是不同的实例（虽然mock返回的是同一个对象，但调用次数应该增加）
    assert mock_create_react_agent.call_count == 2


def test_config_update_detection(temp_config_file, mock_llm, mock_create_react_agent):
    """测试配置更新检测"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    
    # 创建Agent（会缓存）
    agent1 = AgentFactory.create_agent("test_agent")
    
    # 修改配置文件
    time.sleep(0.1)  # 确保修改时间不同
    with open(temp_config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    config["agents"]["test_agent"]["name"] = "更新后的测试智能体"
    with open(temp_config_file, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True)
    
    # 再次创建Agent（应该检测到配置更新并清除缓存）
    agent2 = AgentFactory.create_agent("test_agent")
    
    # create_react_agent应该被调用两次（第一次创建，第二次因为缓存清除后重新创建）
    assert mock_create_react_agent.call_count == 2


def test_reload_agent(temp_config_file, mock_llm, mock_create_react_agent):
    """测试重新加载Agent"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    
    # 创建Agent
    agent1 = AgentFactory.create_agent("test_agent")
    
    # 重新加载Agent
    agent2 = AgentFactory.reload_agent("test_agent")
    
    # create_react_agent应该被调用两次
    assert mock_create_react_agent.call_count == 2


def test_reload_all_agents(temp_config_file, mock_llm, mock_create_react_agent):
    """测试重新加载所有Agent"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    
    # 创建Agent
    agent1 = AgentFactory.create_agent("test_agent")
    
    # 重新加载所有Agent
    agents = AgentFactory.reload_all_agents()
    
    # 应该包含test_agent
    assert "test_agent" in agents
    
    # create_react_agent应该被调用两次（第一次创建，第二次重新加载）
    assert mock_create_react_agent.call_count == 2


def test_clear_cache(temp_config_file, mock_llm, mock_create_react_agent):
    """测试清除缓存"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    
    # 创建Agent（会缓存）
    agent1 = AgentFactory.create_agent("test_agent")
    
    # 验证已缓存
    assert AgentFactory.is_cached("test_agent")
    
    # 清除缓存
    AgentFactory.clear_cache("test_agent")
    
    # 验证缓存已清除
    assert not AgentFactory.is_cached("test_agent")


def test_clear_all_cache(temp_config_file, mock_llm, mock_create_react_agent):
    """测试清除所有缓存"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    
    # 创建Agent（会缓存）
    agent1 = AgentFactory.create_agent("test_agent")
    
    # 验证已缓存
    assert AgentFactory.is_cached("test_agent")
    
    # 清除所有缓存
    AgentFactory.clear_cache()
    
    # 验证缓存已清除
    assert not AgentFactory.is_cached("test_agent")


def test_cache_stats(temp_config_file, mock_llm, mock_create_react_agent):
    """测试缓存统计"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    
    # 创建Agent（缓存未命中）
    agent1 = AgentFactory.create_agent("test_agent")
    
    # 再次创建Agent（缓存命中）
    agent2 = AgentFactory.create_agent("test_agent")
    
    # 获取统计信息
    stats = AgentFactory.get_cache_stats()
    
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["created"] == 1
    assert stats["cache_size"] == 1
    assert "test_agent" in stats["cached_agents"]
    assert stats["hit_rate"] > 0


def test_is_cached(temp_config_file, mock_llm, mock_create_react_agent):
    """测试检查Agent是否已缓存"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    
    # 创建Agent前应该未缓存
    assert not AgentFactory.is_cached("test_agent")
    
    # 创建Agent（会缓存）
    agent = AgentFactory.create_agent("test_agent")
    
    # 应该已缓存
    assert AgentFactory.is_cached("test_agent")


def test_reload_nonexistent_agent(temp_config_file):
    """测试重新加载不存在的Agent"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    
    # 尝试重新加载不存在的Agent应该抛出异常
    with pytest.raises(ValueError, match="智能体配置不存在"):
        AgentFactory.reload_agent("nonexistent_agent")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

