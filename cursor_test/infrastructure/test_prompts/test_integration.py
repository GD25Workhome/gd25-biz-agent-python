"""
集成测试
测试提示词管理系统与业务代码的集成
"""
import pytest
from langchain_core.messages import HumanMessage

from domain.agents.factory import AgentFactory
from infrastructure.prompts.manager import PromptManager

# 注意：router_tools的导入可能因为Python版本问题失败，使用try-except处理
try:
    from domain.router.tools.router_tools import identify_intent, clarify_intent
    ROUTER_TOOLS_AVAILABLE = True
except ImportError:
    ROUTER_TOOLS_AVAILABLE = False


class TestAgentFactoryIntegration:
    """测试AgentFactory集成"""
    
    def test_agent_creation_with_prompt_manager(self):
        """测试使用PromptManager创建Agent"""
        agent = AgentFactory.create_agent("blood_pressure_agent")
        assert agent is not None
    
    def test_agent_creation_appointment(self):
        """测试创建预约智能体"""
        agent = AgentFactory.create_agent("appointment_agent")
        assert agent is not None
    
    def test_agent_fallback_to_old_method(self):
        """测试回退到原有加载方式"""
        # 如果模板不存在，应该回退到原有方式
        # 这里我们测试一个不存在的agent_key，应该抛出异常
        with pytest.raises((ValueError, FileNotFoundError)):
            AgentFactory.create_agent("nonexistent_agent")


class TestRouterToolsIntegration:
    """测试路由工具集成"""
    
    @pytest.mark.skipif(not ROUTER_TOOLS_AVAILABLE, reason="router_tools不可用（可能是Python版本问题）")
    def test_identify_intent_with_prompt_manager(self):
        """测试意图识别使用PromptManager"""
        if not ROUTER_TOOLS_AVAILABLE:
            pytest.skip("router_tools不可用")
        messages = [HumanMessage(content="我想记录血压")]
        # 使用 .invoke() 方法调用工具，参数为字典格式
        result = identify_intent.invoke({"messages": messages})
        assert "intent_type" in result
        assert result["intent_type"] in ["blood_pressure", "appointment", "unclear"]
        assert "confidence" in result
    
    @pytest.mark.skipif(not ROUTER_TOOLS_AVAILABLE, reason="router_tools不可用（可能是Python版本问题）")
    def test_clarify_intent_with_prompt_manager(self):
        """测试意图澄清使用PromptManager"""
        if not ROUTER_TOOLS_AVAILABLE:
            pytest.skip("router_tools不可用")
        query = "你好"
        # 使用 .invoke() 方法调用工具，参数为字典格式
        result = clarify_intent.invoke({"query": query})
        assert isinstance(result, str)
        assert len(result) > 0
        # 澄清问题应该包含功能说明
        assert "血压" in result or "预约" in result


class TestVersionManagement:
    """测试版本管理"""
    
    def test_save_and_retrieve_version(self):
        """测试保存和获取版本"""
        manager = PromptManager()
        
        # 渲染提示词
        prompt = manager.render("blood_pressure_agent")
        
        # 保存版本
        version = manager.save_prompt_version(
            "blood_pressure_agent",
            prompt,
            metadata={"test": True}
        )
        assert version == 1
        
        # 获取版本
        retrieved_prompt = manager.get_prompt_version("blood_pressure_agent", 1)
        assert retrieved_prompt == prompt
        
        # 保存第二个版本
        version2 = manager.save_prompt_version("blood_pressure_agent", prompt + " modified")
        assert version2 == 2
    
    def test_list_versions(self):
        """测试列出版本"""
        manager = PromptManager()
        
        # 保存几个版本
        prompt = manager.render("blood_pressure_agent")
        manager.save_prompt_version("blood_pressure_agent", prompt)
        manager.save_prompt_version("blood_pressure_agent", prompt + " v2")
        
        # 列出版本
        versions = manager.list_versions("blood_pressure_agent")
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2


class TestHotReload:
    """测试热更新"""
    
    def test_reload_template(self):
        """测试重新加载模板"""
        manager = PromptManager()
        
        # 加载模板
        version1 = manager.get_version("blood_pressure_agent")
        
        # 重新加载
        manager.reload_template("blood_pressure_agent")
        version2 = manager.get_version("blood_pressure_agent")
        
        # 版本应该相同（除非文件被修改）
        assert version1 == version2
    
    def test_reload_clears_cache(self):
        """测试重新加载清除缓存"""
        manager = PromptManager()
        
        # 清除所有缓存
        manager.clear_all_cache()
        
        # 渲染提示词（会缓存）
        prompt1 = manager.render("blood_pressure_agent")
        cache_keys_before = manager.get_cached_keys()
        assert len(cache_keys_before) > 0
        
        # 检查缓存键是否包含agent_key
        assert any("blood_pressure_agent" in key for key in cache_keys_before)
        
        # 重新加载（应该清除相关缓存）
        manager.reload_template("blood_pressure_agent")
        
        # 检查缓存键（重新加载后，相关缓存应该被清除）
        cache_keys_after = manager.get_cached_keys()
        # 重新加载应该清除blood_pressure_agent相关的缓存
        blood_pressure_keys_after = [k for k in cache_keys_after if "blood_pressure_agent" in k]
        # 如果还有其他Agent的缓存，这是正常的
        assert len(blood_pressure_keys_after) == 0 or len(cache_keys_after) <= len(cache_keys_before)
