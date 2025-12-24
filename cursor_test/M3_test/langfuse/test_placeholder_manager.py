"""
PlaceholderManager 单元测试
"""
import pytest
from datetime import datetime

# 添加项目根目录到路径
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.prompts.placeholder import PlaceholderManager


def test_system_placeholders():
    """测试系统占位符提取"""
    state = {
        "messages": [],
        "current_intent": None,
        "current_agent": None,
        "need_reroute": False,
        "session_id": "session_456",
        "user_id": "user_123",
    }
    
    placeholders = PlaceholderManager.get_placeholders("test_agent", state)
    
    assert placeholders["user_id"] == "user_123"
    assert placeholders["session_id"] == "session_456"
    assert "current_date" in placeholders
    assert "current_time" in placeholders
    assert "current_datetime" in placeholders
    
    # 验证日期格式
    assert len(placeholders["current_date"]) == 10  # YYYY-MM-DD
    assert len(placeholders["current_time"]) == 8  # HH:MM:SS


def test_agent_specific_placeholders():
    """测试Agent特定占位符"""
    config = {
        "placeholders": {
            "normal_range": "90-140/60-90",
            "measurement_time_format": "YYYY-MM-DD HH:mm"
        }
    }
    
    PlaceholderManager.load_agent_placeholders("test_agent", config)
    
    state = {
        "messages": [],
        "current_intent": None,
        "current_agent": None,
        "need_reroute": False,
        "session_id": "",
        "user_id": "",
    }
    
    placeholders = PlaceholderManager.get_placeholders("test_agent", state)
    
    assert placeholders["normal_range"] == "90-140/60-90"
    assert placeholders["measurement_time_format"] == "YYYY-MM-DD HH:mm"


def test_fill_placeholders():
    """测试占位符填充"""
    template = "用户ID: {{user_id}}, 会话ID: {{session_id}}, 正常范围: {{normal_range}}"
    
    placeholders = {
        "user_id": "user_123",
        "session_id": "session_456",
        "normal_range": "90-140/60-90"
    }
    
    result = PlaceholderManager.fill_placeholders(template, placeholders)
    
    assert "user_123" in result
    assert "session_456" in result
    assert "90-140/60-90" in result
    assert "{{user_id}}" not in result
    assert "{{session_id}}" not in result


def test_fill_placeholders_without_state():
    """测试在没有state的情况下获取占位符"""
    placeholders = PlaceholderManager.get_placeholders("test_agent", state=None)
    
    # 应该只有时间相关的占位符
    assert "current_date" in placeholders
    assert "current_time" in placeholders
    assert "current_datetime" in placeholders
    # 不应该有user_id和session_id
    assert "user_id" not in placeholders
    assert "session_id" not in placeholders


def test_clear_agent_placeholders():
    """测试清除Agent占位符"""
    config = {
        "placeholders": {
            "test_key": "test_value"
        }
    }
    
    PlaceholderManager.load_agent_placeholders("test_agent", config)
    assert "test_agent" in PlaceholderManager.AGENT_PLACEHOLDERS
    
    PlaceholderManager.clear_agent_placeholders("test_agent")
    assert "test_agent" not in PlaceholderManager.AGENT_PLACEHOLDERS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

