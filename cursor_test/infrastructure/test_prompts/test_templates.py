"""
模板文件测试
测试实际创建的模板文件是否能正常加载和渲染
"""
import pytest
from infrastructure.prompts.manager import PromptManager


class TestTemplates:
    """测试模板文件"""
    
    def test_blood_pressure_agent_template(self):
        """测试血压智能体模板"""
        manager = PromptManager()
        
        # 加载模板
        template = manager.load_template("blood_pressure_agent")
        assert template.agent_key == "blood_pressure_agent"
        assert template.version == "1.0.0"
        assert len(template.modules) > 0
        
        # 测试渲染（无上下文）
        prompt = manager.render("blood_pressure_agent")
        assert len(prompt) > 0
        assert "血压" in prompt
        assert "记录" in prompt or "查询" in prompt
        
        # 测试渲染（带上下文）
        context = {
            "user_id": "user123",
            "collected_fields": "收缩压=120；舒张压=80",
            "missing_fields": "无"
        }
        prompt_with_context = manager.render("blood_pressure_agent", context=context)
        assert "user123" in prompt_with_context
        assert "已收集字段" in prompt_with_context
    
    def test_appointment_agent_template(self):
        """测试预约智能体模板"""
        manager = PromptManager()
        
        # 加载模板
        template = manager.load_template("appointment_agent")
        assert template.agent_key == "appointment_agent"
        assert template.version == "1.0.0"
        assert len(template.modules) > 0
        
        # 测试渲染
        prompt = manager.render("appointment_agent")
        assert len(prompt) > 0
        assert "预约" in prompt or "复诊" in prompt
        
        # 测试渲染（带上下文）
        context = {"user_id": "user123"}
        prompt_with_context = manager.render("appointment_agent", context=context)
        assert "user123" in prompt_with_context
    
    def test_router_tools_template(self):
        """测试路由工具模板"""
        manager = PromptManager()
        
        # 加载模板
        template = manager.load_template("router_tools")
        assert template.agent_key == "router_tools"
        assert template.version == "1.0.0"
        assert len(template.modules) >= 2
        
        # 测试渲染意图识别模块
        prompt = manager.render("router_tools", include_modules=["intent_identification"])
        assert len(prompt) > 0
        assert "意图" in prompt or "路由" in prompt
        
        # 测试渲染澄清模块
        prompt = manager.render("router_tools", include_modules=["clarify_intent"])
        assert len(prompt) > 0
        assert "澄清" in prompt or "友好" in prompt
