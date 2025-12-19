"""
提示词管理器单元测试
"""
import pytest
import tempfile
import yaml
import os
from pathlib import Path

from infrastructure.prompts.manager import PromptManager


@pytest.fixture
def temp_templates_dir():
    """创建临时模板目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        templates_dir = Path(tmpdir) / "templates"
        templates_dir.mkdir(parents=True)
        yield str(templates_dir)


@pytest.fixture
def sample_template_file(temp_templates_dir):
    """创建示例模板文件"""
    template_file = Path(temp_templates_dir) / "test_agent.yaml"
    
    template_data = {
        "agent_key": "test_agent",
        "version": "1.0.0",
        "modules": {
            "role": {
                "type": "required",
                "loader": "config",
                "source": str(Path(temp_templates_dir).parent / "modules" / "role.txt"),
                "enabled": True
            },
            "user_info": {
                "type": "optional",
                "loader": "dynamic",
                "source": "runtime",
                "enabled": True,
                "condition": "{user_id is not None}",
                "template": "系统提供的用户ID：{user_id}。"
            }
        },
        "composition": {
            "order": ["role", "user_info"],
            "separator": "\n\n"
        }
    }
    
    # 创建模块文件
    modules_dir = Path(temp_templates_dir).parent / "modules"
    modules_dir.mkdir(parents=True, exist_ok=True)
    role_file = modules_dir / "role.txt"
    role_file.write_text("你是一个测试助手。", encoding="utf-8")
    
    # 写入模板文件
    with open(template_file, "w", encoding="utf-8") as f:
        yaml.dump(template_data, f, allow_unicode=True)
    
    return template_file


class TestPromptManager:
    """测试PromptManager"""
    
    def test_init(self, temp_templates_dir):
        """测试初始化"""
        manager = PromptManager(templates_dir=temp_templates_dir)
        assert manager is not None
    
    def test_load_template(self, temp_templates_dir, sample_template_file):
        """测试加载模板"""
        manager = PromptManager(templates_dir=temp_templates_dir)
        template = manager.load_template("test_agent")
        assert template.agent_key == "test_agent"
        assert template.version == "1.0.0"
        assert len(template.modules) == 2
    
    def test_load_template_not_found(self, temp_templates_dir):
        """测试加载不存在的模板"""
        manager = PromptManager(templates_dir=temp_templates_dir)
        with pytest.raises(FileNotFoundError):
            manager.load_template("nonexistent_agent")
    
    def test_render_prompt(self, temp_templates_dir, sample_template_file):
        """测试渲染提示词"""
        manager = PromptManager(templates_dir=temp_templates_dir)
        prompt = manager.render("test_agent")
        assert len(prompt) > 0
        assert "测试助手" in prompt
    
    def test_render_with_context(self, temp_templates_dir, sample_template_file):
        """测试带上下文的渲染"""
        manager = PromptManager(templates_dir=temp_templates_dir)
        context = {"user_id": "user123"}
        prompt = manager.render("test_agent", context=context)
        assert "user123" in prompt
        assert "系统提供的用户ID" in prompt
    
    def test_render_without_context(self, temp_templates_dir, sample_template_file):
        """测试无上下文渲染（条件不满足）"""
        manager = PromptManager(templates_dir=temp_templates_dir)
        prompt = manager.render("test_agent", context={})
        # user_info模块因为条件不满足应该被跳过
        assert "测试助手" in prompt
        assert "系统提供的用户ID" not in prompt
    
    def test_render_include_modules(self, temp_templates_dir, sample_template_file):
        """测试包含特定模块"""
        manager = PromptManager(templates_dir=temp_templates_dir)
        context = {"user_id": "user123"}
        prompt = manager.render(
            "test_agent",
            context=context,
            include_modules=["role"]
        )
        assert "测试助手" in prompt
        assert "系统提供的用户ID" not in prompt  # 被排除
    
    def test_render_exclude_modules(self, temp_templates_dir, sample_template_file):
        """测试排除特定模块"""
        manager = PromptManager(templates_dir=temp_templates_dir)
        prompt = manager.render(
            "test_agent",
            exclude_modules=["user_info"]
        )
        assert "测试助手" in prompt
        assert "系统提供的用户ID" not in prompt
    
    def test_cache(self, temp_templates_dir, sample_template_file):
        """测试缓存功能"""
        manager = PromptManager(templates_dir=temp_templates_dir)
        
        # 第一次渲染
        prompt1 = manager.render("test_agent")
        cache_keys1 = manager.get_cached_keys()
        assert len(cache_keys1) > 0
        
        # 第二次渲染（应该使用缓存）
        prompt2 = manager.render("test_agent")
        assert prompt1 == prompt2
        cache_keys2 = manager.get_cached_keys()
        assert len(cache_keys1) == len(cache_keys2)
    
    def test_reload_template(self, temp_templates_dir, sample_template_file):
        """测试重新加载模板"""
        manager = PromptManager(templates_dir=temp_templates_dir)
        version1 = manager.get_version("test_agent")
        
        # 修改模板文件
        template_file = Path(temp_templates_dir) / "test_agent.yaml"
        with open(template_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        data["version"] = "1.0.1"
        with open(template_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True)
        
        # 重新加载
        manager.reload_template("test_agent")
        version2 = manager.get_version("test_agent")
        assert version2 == "1.0.1"
    
    def test_get_version(self, temp_templates_dir, sample_template_file):
        """测试获取版本"""
        manager = PromptManager(templates_dir=temp_templates_dir)
        version = manager.get_version("test_agent")
        assert version == "1.0.0"
    
    def test_clear_cache(self, temp_templates_dir, sample_template_file):
        """测试清除缓存"""
        manager = PromptManager(templates_dir=temp_templates_dir)
        manager.render("test_agent")
        assert len(manager.get_cached_keys()) > 0
        
        manager.clear_all_cache()
        assert len(manager.get_cached_keys()) == 0
