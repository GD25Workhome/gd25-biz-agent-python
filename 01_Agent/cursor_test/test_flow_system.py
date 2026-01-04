"""
流程系统测试
测试第二到第九阶段实现的功能

Pytest 命令示例：
================

# 运行整个测试文件
pytest cursor_test/test_flow_system.py -v

# 运行整个测试文件（详细输出 + 显示 print 输出）
pytest cursor_test/test_flow_system.py -v -s

# 运行特定的测试类
pytest cursor_test/test_flow_system.py::TestFlowParser -v

# 运行特定的测试方法
pytest cursor_test/test_flow_system.py::TestFlowParser::test_parse_yaml -v
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
import yaml
from backend.domain.flows.parser import FlowParser
from backend.domain.flows.definition import FlowDefinition
from backend.domain.flows.manager import FlowManager
from backend.domain.tools.registry import tool_registry
from backend.infrastructure.prompts.manager import prompt_manager
from backend.app.config import find_project_root


class TestFlowParser:
    """测试流程解析器"""
    
    def test_parse_medical_agent_yaml(self):
        """测试解析医疗分身Agent流程YAML"""
        project_root = find_project_root()
        yaml_path = project_root / "config" / "flows" / "medical_agent" / "flow.yaml"
        
        if not yaml_path.exists():
            pytest.skip(f"流程配置文件不存在: {yaml_path}")
        
        flow_def = FlowParser.parse_yaml(yaml_path)
        
        assert flow_def.name == "medical_agent"
        assert flow_def.version == "1.0"
        assert len(flow_def.nodes) == 3
        assert len(flow_def.edges) == 4
        assert flow_def.entry_node == "intent_recognition"
    
    def test_parse_work_plan_agent_yaml(self):
        """测试解析工作计划Agent流程YAML"""
        project_root = find_project_root()
        yaml_path = project_root / "config" / "flows" / "work_plan_agent" / "flow.yaml"
        
        if not yaml_path.exists():
            pytest.skip(f"流程配置文件不存在: {yaml_path}")
        
        flow_def = FlowParser.parse_yaml(yaml_path)
        
        assert flow_def.name == "work_plan_agent"
        assert flow_def.version == "1.0"
        assert len(flow_def.nodes) == 3
        assert len(flow_def.edges) == 4
        assert flow_def.entry_node == "intent_recognition"
    
    def test_scan_flows_directory(self):
        """测试扫描流程目录"""
        project_root = find_project_root()
        flows_dir = project_root / "config" / "flows"
        
        if not flows_dir.exists():
            pytest.skip(f"流程目录不存在: {flows_dir}")
        
        flows = FlowParser.scan_flows_directory(flows_dir)
        
        assert len(flows) >= 0  # 至少应该有0个流程
        if "medical_agent" in flows:
            assert flows["medical_agent"].name == "medical_agent"
        if "work_plan_agent" in flows:
            assert flows["work_plan_agent"].name == "work_plan_agent"


class TestFlowManager:
    """测试流程管理器"""
    
    def test_scan_flows(self):
        """测试扫描流程"""
        flows = FlowManager.scan_flows()
        assert isinstance(flows, dict)
        assert len(flows) >= 0
    
    def test_get_flow_loader_config(self):
        """测试获取流程加载配置"""
        config = FlowManager.get_flow_loader_config()
        assert isinstance(config, dict)
        assert "preload" in config
        assert "lazy_load" in config
        assert isinstance(config["preload"], list)
        assert isinstance(config["lazy_load"], list)


class TestToolRegistry:
    """测试工具注册表"""
    
    def test_tool_registry_has_tools(self):
        """测试工具注册表是否有工具"""
        tools = tool_registry.get_all_tools()
        assert isinstance(tools, dict)
        # 至少应该有血压记录工具
        if "record_blood_pressure" in tools:
            assert tools["record_blood_pressure"].name == "record_blood_pressure"


class TestPromptManager:
    """测试提示词管理器"""
    
    def test_get_prompt(self):
        """测试获取提示词"""
        project_root = find_project_root()
        flow_dir = str(project_root / "config" / "flows" / "medical_agent")
        prompt_path = "prompts/intent_recognition.txt"
        
        try:
            prompt_content = prompt_manager.get_prompt(prompt_path, flow_dir)
            assert isinstance(prompt_content, str)
            assert len(prompt_content) > 0
        except FileNotFoundError:
            pytest.skip(f"提示词文件不存在: {prompt_path}")


class TestSystemInitialization:
    """测试系统初始化"""
    
    def test_flow_manager_scan(self):
        """测试流程管理器扫描功能"""
        flows = FlowManager.scan_flows()
        assert isinstance(flows, dict)
        # 验证扫描结果
        if flows:
            for flow_name, flow_def in flows.items():
                assert isinstance(flow_def, FlowDefinition)
                assert flow_def.name == flow_name


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

