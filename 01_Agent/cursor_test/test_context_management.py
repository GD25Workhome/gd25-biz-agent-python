"""
测试上下文管理功能（里程碑3）

运行命令：
    pytest cursor_test/test_context_management.py -v
"""
import pytest
from backend.domain.context.flow_context import FlowContext
from backend.domain.context.user_context import UserContext
from backend.domain.context.manager import ContextManager, get_context_manager


class TestFlowContext:
    """测试FlowContext"""
    
    def test_create_flow_context(self):
        """测试创建FlowContext"""
        context = FlowContext()
        assert context is not None
        assert context.data == {}
    
    def test_set_and_get(self):
        """测试设置和获取数据"""
        context = FlowContext()
        context.set("key1", "value1")
        assert context.get("key1") == "value1"
        assert context.get("key2", "default") == "default"
    
    def test_update(self):
        """测试批量更新"""
        context = FlowContext()
        context.update({"key1": "value1", "key2": "value2"})
        assert context.get("key1") == "value1"
        assert context.get("key2") == "value2"
    
    def test_clear(self):
        """测试清空数据"""
        context = FlowContext()
        context.set("key1", "value1")
        context.clear()
        assert context.data == {}
    
    def test_remove(self):
        """测试移除数据"""
        context = FlowContext()
        context.set("key1", "value1")
        value = context.remove("key1")
        assert value == "value1"
        assert context.get("key1") is None
    
    def test_has(self):
        """测试检查键是否存在"""
        context = FlowContext()
        context.set("key1", "value1")
        assert context.has("key1") is True
        assert context.has("key2") is False


class TestUserContext:
    """测试UserContext"""
    
    def test_create_user_context(self):
        """测试创建UserContext"""
        context = UserContext("user123")
        assert context.user_id == "user123"
        assert context.get("user_id") == "user123"
    
    def test_preferences(self):
        """测试用户偏好"""
        context = UserContext("user123")
        context.set_preference("language", "zh-CN")
        assert context.get_preference("language") == "zh-CN"
        assert context.get_preference("theme", "dark") == "dark"
    
    def test_settings(self):
        """测试用户设置"""
        context = UserContext("user123")
        context.set_setting("notifications", True)
        assert context.get_setting("notifications") is True
        assert context.get_setting("auto_save", False) is False
    
    def test_user_info(self):
        """测试用户信息"""
        context = UserContext("user123")
        user_info = {"name": "测试用户", "age": 30}
        context.set_user_info(user_info)
        assert context.get_user_info() == user_info
    
    def test_update(self):
        """测试批量更新"""
        context = UserContext("user123")
        context.update({
            "preferences": {"language": "zh-CN"},
            "settings": {"theme": "dark"},
            "custom_key": "custom_value"
        })
        assert context.get_preference("language") == "zh-CN"
        assert context.get_setting("theme") == "dark"
        assert context.get("custom_key") == "custom_value"


class TestContextManager:
    """测试ContextManager"""
    
    def test_create_flow_context(self):
        """测试创建流程上下文"""
        manager = ContextManager()
        context = manager.create_flow_context("flow1")
        assert context is not None
        assert isinstance(context, FlowContext)
    
    def test_get_flow_context(self):
        """测试获取流程上下文"""
        manager = ContextManager()
        context1 = manager.create_flow_context("flow1")
        context2 = manager.get_flow_context("flow1")
        assert context1 is context2
        
        context3 = manager.get_flow_context("flow2")
        assert context3 is None
    
    def test_get_or_create_flow_context(self):
        """测试获取或创建流程上下文"""
        manager = ContextManager()
        context1 = manager.get_or_create_flow_context("flow1")
        context2 = manager.get_or_create_flow_context("flow1")
        assert context1 is context2
    
    def test_create_user_context(self):
        """测试创建用户上下文"""
        manager = ContextManager()
        context1 = manager.create_user_context("user1")
        context2 = manager.create_user_context("user1")
        assert context1 is context2  # 应该返回同一个实例
    
    def test_get_user_context(self):
        """测试获取用户上下文"""
        manager = ContextManager()
        context1 = manager.create_user_context("user1")
        context2 = manager.get_user_context("user1")
        assert context1 is context2
        
        context3 = manager.get_user_context("user2")
        assert context3 is None
    
    def test_clear_flow_context(self):
        """测试清理流程上下文"""
        manager = ContextManager()
        manager.create_flow_context("flow1")
        assert manager.get_flow_context("flow1") is not None
        
        manager.clear_flow_context("flow1")
        assert manager.get_flow_context("flow1") is None
    
    def test_clear_user_context(self):
        """测试清理用户上下文"""
        manager = ContextManager()
        manager.create_user_context("user1")
        assert manager.get_user_context("user1") is not None
        
        manager.clear_user_context("user1")
        assert manager.get_user_context("user1") is None
    
    def test_get_context_manager_singleton(self):
        """测试全局上下文管理器单例"""
        manager1 = get_context_manager()
        manager2 = get_context_manager()
        assert manager1 is manager2

