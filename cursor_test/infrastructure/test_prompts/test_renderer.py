"""
模板渲染器单元测试
"""
import pytest
from infrastructure.prompts.renderer import TemplateRenderer


class TestTemplateRenderer:
    """测试TemplateRenderer"""
    
    def test_render_template_simple(self):
        """测试简单模板渲染"""
        template = "你好，{name}！"
        variables = {"name": "世界"}
        result = TemplateRenderer.render_template(template, variables)
        assert result == "你好，世界！"
    
    def test_render_template_multiple_vars(self):
        """测试多变量模板渲染"""
        template = "{greeting}，{name}！今天是{date}。"
        variables = {
            "greeting": "你好",
            "name": "用户",
            "date": "2025-01-15"
        }
        result = TemplateRenderer.render_template(template, variables)
        assert result == "你好，用户！今天是2025-01-15。"
    
    def test_render_template_no_vars(self):
        """测试无变量模板"""
        template = "这是固定文本"
        variables = {}
        result = TemplateRenderer.render_template(template, variables)
        assert result == "这是固定文本"
    
    def test_render_template_missing_var(self):
        """测试缺失变量"""
        template = "你好，{name}！"
        variables = {}
        result = TemplateRenderer.render_template(template, variables)
        assert result == "你好，{name}！"  # 变量未替换
    
    def test_evaluate_condition_simple(self):
        """测试简单条件评估"""
        condition = "{user_id is not None}"
        context = {"user_id": "user123"}
        result = TemplateRenderer.evaluate_condition(condition, context)
        assert result is True
        
        context = {"user_id": None}
        result = TemplateRenderer.evaluate_condition(condition, context)
        assert result is False
        
        # 测试变量不在上下文中的情况（启动时场景）
        # 应该将变量替换为 None，条件评估为 False，不产生警告
        context = {}
        result = TemplateRenderer.evaluate_condition(condition, context)
        assert result is False  # None is not None 为 False
    
    def test_evaluate_condition_comparison(self):
        """测试比较条件"""
        condition = "{len(missing_fields) > 0}"
        context = {"missing_fields": ["field1", "field2"]}
        result = TemplateRenderer.evaluate_condition(condition, context)
        assert result is True
        
        context = {"missing_fields": []}
        result = TemplateRenderer.evaluate_condition(condition, context)
        assert result is False
    
    def test_evaluate_condition_equality(self):
        """测试相等条件"""
        condition = "{agent_type == 'blood_pressure'}"
        context = {"agent_type": "blood_pressure"}
        result = TemplateRenderer.evaluate_condition(condition, context)
        assert result is True
        
        context = {"agent_type": "appointment"}
        result = TemplateRenderer.evaluate_condition(condition, context)
        assert result is False
    
    def test_evaluate_condition_invalid(self):
        """测试无效条件"""
        condition = "{invalid syntax!!!}"
        context = {}
        result = TemplateRenderer.evaluate_condition(condition, context)
        assert result is False  # 应该返回False而不是抛出异常
    
    def test_compose_modules(self):
        """测试模块组合"""
        modules_content = {
            "role": "你是助手",
            "function": "功能说明",
            "notes": "注意事项"
        }
        order = ["role", "function", "notes"]
        result = TemplateRenderer.compose_modules(modules_content, order)
        assert "你是助手" in result
        assert "功能说明" in result
        assert "注意事项" in result
    
    def test_compose_modules_custom_separator(self):
        """测试自定义分隔符"""
        modules_content = {
            "module1": "内容1",
            "module2": "内容2"
        }
        order = ["module1", "module2"]
        result = TemplateRenderer.compose_modules(modules_content, order, separator="\n---\n")
        assert "内容1\n---\n内容2" in result
    
    def test_compose_modules_partial_order(self):
        """测试部分顺序"""
        modules_content = {
            "role": "角色",
            "function": "功能",
            "extra": "额外"
        }
        order = ["role", "function"]  # 只指定部分顺序
        result = TemplateRenderer.compose_modules(modules_content, order)
        # extra应该在最后
        assert result.startswith("角色")
        assert "额外" in result
