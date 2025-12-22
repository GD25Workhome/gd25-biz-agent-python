"""
测试所有Agent的Langfuse提示词加载
验证所有配置的Langfuse提示词模版是否都能正常获取
"""
import pytest
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from domain.agents.factory import AgentFactory
from infrastructure.prompts.langfuse_adapter import LangfusePromptAdapter, LANGFUSE_AVAILABLE
from app.core.config import settings


@pytest.fixture
def mock_langfuse_client():
    """Mock Langfuse客户端"""
    if not LANGFUSE_AVAILABLE:
        pytest.skip("Langfuse未安装")
    
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


def test_all_agents_have_langfuse_template_config():
    """测试所有Agent都配置了langfuse_template"""
    # 加载配置
    AgentFactory.load_config()
    config = AgentFactory._config
    
    # 定义所有应该配置Langfuse模版的Agent
    agents_with_langfuse = [
        "blood_pressure_agent",
        "appointment_agent",
        "health_event_agent",
        "medication_agent",
        "symptom_agent",
    ]
    
    missing_configs = []
    for agent_key in agents_with_langfuse:
        if agent_key not in config:
            missing_configs.append(f"{agent_key} (配置不存在)")
            continue
        
        agent_config = config[agent_key]
        if "langfuse_template" not in agent_config:
            missing_configs.append(f"{agent_key} (缺少langfuse_template)")
    
    if missing_configs:
        pytest.fail(f"以下Agent缺少Langfuse模版配置: {', '.join(missing_configs)}")
    
    # 验证所有Agent都有配置
    assert len(missing_configs) == 0, "所有Agent都应该配置Langfuse模版"


def test_langfuse_template_names():
    """测试Langfuse模版名称格式"""
    AgentFactory.load_config()
    config = AgentFactory._config
    
    expected_templates = {
        "blood_pressure_agent": "blood_pressure_agent_prompt",
        "appointment_agent": "appointment_agent_prompt",
        "health_event_agent": "health_event_agent_prompt",
        "medication_agent": "medication_agent_prompt",
        "symptom_agent": "symptom_agent_prompt",
    }
    
    for agent_key, expected_template in expected_templates.items():
        if agent_key not in config:
            continue
        
        agent_config = config[agent_key]
        if "langfuse_template" in agent_config:
            actual_template = agent_config["langfuse_template"]
            assert actual_template == expected_template, \
                f"{agent_key}的模版名称应该是{expected_template}，实际是{actual_template}"


@pytest.mark.skipif(not LANGFUSE_AVAILABLE, reason="Langfuse未安装")
def test_load_prompts_from_langfuse(mock_langfuse_client, mock_settings):
    """测试从Langfuse加载所有Agent的提示词"""
    AgentFactory.load_config()
    config = AgentFactory._config
    
    # 定义所有应该从Langfuse加载的Agent
    agents_to_test = [
        "blood_pressure_agent",
        "appointment_agent",
        "health_event_agent",
        "medication_agent",
        "symptom_agent",
    ]
    
    # Mock每个Agent的提示词内容
    template_contents = {
        "blood_pressure_agent_prompt": "血压记录助手提示词",
        "appointment_agent_prompt": "复诊管理助手提示词",
        "health_event_agent_prompt": "健康事件记录助手提示词",
        "medication_agent_prompt": "用药记录助手提示词",
        "symptom_agent_prompt": "症状记录助手提示词",
    }
    
    # 设置Mock返回值
    def mock_get_prompt(template_name, version=None):
        mock_prompt = MagicMock()
        content = template_contents.get(template_name, f"{template_name}的提示词")
        mock_prompt.prompt = content
        return mock_prompt
    
    mock_langfuse_client.get_prompt.side_effect = mock_get_prompt
    
    # 测试每个Agent的提示词加载
    failed_agents = []
    for agent_key in agents_to_test:
        if agent_key not in config:
            failed_agents.append(f"{agent_key} (配置不存在)")
            continue
        
        agent_config = config[agent_key]
        if "langfuse_template" not in agent_config:
            failed_agents.append(f"{agent_key} (未配置langfuse_template)")
            continue
        
        template_name = agent_config["langfuse_template"]
        template_version = agent_config.get("langfuse_template_version")
        
        try:
            # 创建适配器并获取模版
            adapter = LangfusePromptAdapter()
            template = adapter.get_template(template_name, version=template_version)
            
            # 验证模版内容不为空
            assert template is not None, f"{agent_key}的提示词为空"
            assert len(template) > 0, f"{agent_key}的提示词长度为0"
            
            print(f"✅ {agent_key}: 成功加载提示词 (长度: {len(template)})")
            
        except Exception as e:
            failed_agents.append(f"{agent_key} (错误: {str(e)})")
            print(f"❌ {agent_key}: 加载失败 - {str(e)}")
    
    if failed_agents:
        pytest.fail(f"以下Agent的提示词加载失败: {', '.join(failed_agents)}")
    
    # 验证所有Agent都成功加载
    assert len(failed_agents) == 0, "所有Agent的提示词都应该成功加载"


def test_placeholder_configuration():
    """测试占位符配置"""
    AgentFactory.load_config()
    config = AgentFactory._config
    
    # blood_pressure_agent应该有占位符配置
    if "blood_pressure_agent" in config:
        agent_config = config["blood_pressure_agent"]
        if "placeholders" in agent_config:
            placeholders = agent_config["placeholders"]
            assert "normal_range" in placeholders, "blood_pressure_agent应该有normal_range占位符"
            assert "measurement_time_format" in placeholders, "blood_pressure_agent应该有measurement_time_format占位符"
            print(f"✅ blood_pressure_agent占位符配置正确: {list(placeholders.keys())}")


def test_fallback_configuration():
    """测试降级配置（system_prompt_path）"""
    AgentFactory.load_config()
    config = AgentFactory._config
    
    agents_to_test = [
        "blood_pressure_agent",
        "appointment_agent",
        "health_event_agent",
        "medication_agent",
        "symptom_agent",
    ]
    
    missing_fallbacks = []
    for agent_key in agents_to_test:
        if agent_key not in config:
            continue
        
        agent_config = config[agent_key]
        # 检查是否有降级配置
        has_fallback = "system_prompt_path" in agent_config or "system_prompt" in agent_config
        
        if not has_fallback:
            missing_fallbacks.append(agent_key)
    
    if missing_fallbacks:
        pytest.fail(f"以下Agent缺少降级配置: {', '.join(missing_fallbacks)}")
    
    print(f"✅ 所有Agent都有降级配置")


def test_template_version_configuration():
    """测试模版版本配置"""
    AgentFactory.load_config()
    config = AgentFactory._config
    
    agents_with_version = []
    agents_without_version = []
    
    for agent_key, agent_config in config.items():
        if "langfuse_template" in agent_config:
            if "langfuse_template_version" in agent_config:
                agents_with_version.append(agent_key)
            else:
                agents_without_version.append(agent_key)
    
    print(f"✅ 配置了版本的Agent: {agents_with_version}")
    if agents_without_version:
        print(f"⚠️  未配置版本的Agent（将使用最新版本）: {agents_without_version}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

