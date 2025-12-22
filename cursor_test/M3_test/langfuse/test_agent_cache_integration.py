"""
Agent缓存机制集成测试
测试Agent缓存在实际场景中的使用
"""
import pytest
import os
import tempfile
import yaml
import time
from unittest.mock import patch, MagicMock
from pathlib import Path

# 添加项目根目录到路径
import sys
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from domain.agents.factory import AgentFactory
from domain.agents.registry import AgentRegistry
from domain.router.graph import create_router_graph
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
else:
    CompiledStateGraph = Any


@pytest.fixture
def temp_config_file():
    """创建临时配置文件"""
    config = {
        "agents": {
            "blood_pressure_agent": {
                "name": "血压记录智能体",
                "llm": {
                    "model": "deepseek-chat",
                    "temperature": 0.7
                },
                "tools": [],
                "system_prompt": "你是一个血压记录助手",
                "routing": {
                    "node_name": "blood_pressure_agent",
                    "intent_type": "blood_pressure"
                }
            },
            "appointment_agent": {
                "name": "复诊管理智能体",
                "llm": {
                    "model": "deepseek-chat",
                    "temperature": 0.0
                },
                "tools": [],
                "system_prompt": "你是一个预约助手",
                "routing": {
                    "node_name": "appointment_agent",
                    "intent_type": "appointment"
                }
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
    # 清除缓存和注册
    AgentFactory.clear_cache()
    AgentFactory._config = {}
    AgentFactory._config_path = "config/agents.yaml"
    AgentFactory._config_mtime = None
    AgentRegistry.clear()


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


def test_agent_cache_in_router_graph(temp_config_file, mock_llm, mock_create_react_agent):
    """测试路由图创建时Agent缓存的使用"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    AgentRegistry.load_from_config(temp_config_file)
    
    # 创建路由图（会创建Agent并缓存）
    graph1 = create_router_graph()
    
    # 获取创建次数
    first_call_count = mock_create_react_agent.call_count
    
    # 再次创建路由图（应该使用缓存的Agent）
    graph2 = create_router_graph()
    
    # create_react_agent不应该被再次调用（因为使用了缓存）
    assert mock_create_react_agent.call_count == first_call_count
    
    # 验证缓存统计
    stats = AgentFactory.get_cache_stats()
    assert stats["cache_size"] >= 2  # 至少缓存了2个Agent


def test_agent_cache_after_config_update(temp_config_file, mock_llm, mock_create_react_agent):
    """测试配置更新后缓存清除"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    AgentRegistry.load_from_config(temp_config_file)
    
    # 创建Agent（会缓存）
    agent1 = AgentFactory.create_agent("blood_pressure_agent")
    first_call_count = mock_create_react_agent.call_count
    
    # 修改配置文件
    time.sleep(0.1)  # 确保修改时间不同
    with open(temp_config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    config["agents"]["blood_pressure_agent"]["name"] = "更新后的血压记录智能体"
    with open(temp_config_file, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True)
    
    # 重新加载配置（应该检测到更新并清除缓存）
    AgentFactory.load_config(temp_config_file)
    
    # 再次创建Agent（应该重新创建，因为缓存已清除）
    agent2 = AgentFactory.create_agent("blood_pressure_agent")
    
    # create_react_agent应该被调用两次
    assert mock_create_react_agent.call_count == first_call_count + 1


def test_agent_reload_in_router_graph(temp_config_file, mock_llm, mock_create_react_agent):
    """测试在路由图创建后重新加载Agent"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    AgentRegistry.load_from_config(temp_config_file)
    
    # 创建路由图（会创建Agent并缓存）
    graph = create_router_graph()
    first_call_count = mock_create_react_agent.call_count
    
    # 重新加载Agent
    AgentFactory.reload_agent("blood_pressure_agent")
    
    # create_react_agent应该被再次调用
    assert mock_create_react_agent.call_count == first_call_count + 1
    
    # 验证缓存统计
    stats = AgentFactory.get_cache_stats()
    assert stats["reloaded"] >= 1


def test_agent_cache_performance(temp_config_file, mock_llm, mock_create_react_agent):
    """测试Agent缓存的性能提升"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    
    # 第一次创建Agent（缓存未命中）
    start_time = time.time()
    agent1 = AgentFactory.create_agent("blood_pressure_agent")
    first_time = time.time() - start_time
    
    # 第二次创建Agent（缓存命中）
    start_time = time.time()
    agent2 = AgentFactory.create_agent("blood_pressure_agent")
    second_time = time.time() - start_time
    
    # 缓存命中应该更快（虽然mock可能很快，但至少调用次数应该不同）
    # 验证缓存统计
    stats = AgentFactory.get_cache_stats()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1


def test_agent_cache_with_multiple_agents(temp_config_file, mock_llm, mock_create_react_agent):
    """测试多个Agent的缓存"""
    # 加载配置
    AgentFactory.load_config(temp_config_file)
    
    # 创建多个Agent
    agent1 = AgentFactory.create_agent("blood_pressure_agent")
    agent2 = AgentFactory.create_agent("appointment_agent")
    
    # 验证都已被缓存
    assert AgentFactory.is_cached("blood_pressure_agent")
    assert AgentFactory.is_cached("appointment_agent")
    
    # 验证缓存统计
    stats = AgentFactory.get_cache_stats()
    assert stats["cache_size"] == 2
    assert len(stats["cached_agents"]) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

