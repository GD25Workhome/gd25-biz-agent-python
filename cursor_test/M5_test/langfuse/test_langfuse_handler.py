"""
测试 Langfuse Handler 集成
验证 Langfuse 集成模块的功能
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from app.core.config import settings
from infrastructure.observability.llm_logger import LlmLogContext
from infrastructure.observability.langfuse_handler import (
    create_langfuse_handler,
    set_langfuse_trace_context,
    is_langfuse_available,
)


class TestLangfuseHandler:
    """测试 Langfuse Handler"""
    
    def test_create_langfuse_handler_with_context(self):
        """测试创建 Langfuse Handler（带上下文）"""
        # 跳过测试如果 Langfuse 未安装
        try:
            from langfuse.langchain import CallbackHandler
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        # 模拟配置
        with patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
             patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
             patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'):
            
            context = LlmLogContext(
                user_id="user_123",
                session_id="session_456",
                agent_key="test_agent",
                trace_id="trace_789"
            )
            
            handler = create_langfuse_handler(context)
            
            assert handler is not None
            assert isinstance(handler, CallbackHandler)
    
    def test_create_langfuse_handler_without_context(self):
        """测试创建 Langfuse Handler（无上下文）"""
        try:
            from langfuse.langchain import CallbackHandler
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        with patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
             patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
             patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'):
            
            handler = create_langfuse_handler(None)
            
            assert handler is not None
            assert isinstance(handler, CallbackHandler)
    
    def test_create_langfuse_handler_not_enabled(self):
        """测试 Langfuse 未启用时创建 Handler"""
        # 如果 Langfuse 未安装，会先抛出 ImportError
        try:
            from langfuse.langchain import CallbackHandler
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        with patch.object(settings, 'LANGFUSE_ENABLED', False):
            with pytest.raises(ValueError, match="Langfuse未启用"):
                create_langfuse_handler(None)
    
    def test_create_langfuse_handler_missing_config(self):
        """测试配置不完整时创建 Handler"""
        # 如果 Langfuse 未安装，会先抛出 ImportError
        try:
            from langfuse.langchain import CallbackHandler
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        with patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'LANGFUSE_PUBLIC_KEY', None), \
             patch.object(settings, 'LANGFUSE_SECRET_KEY', None):
            
            with pytest.raises(ValueError, match="Langfuse配置不完整"):
                create_langfuse_handler(None)
    
    def test_set_langfuse_trace_context(self):
        """测试设置 Trace 上下文"""
        try:
            from langfuse import Langfuse
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        with patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
             patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
             patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'), \
             patch('infrastructure.observability.langfuse_handler._get_langfuse_client') as mock_get_client:
            
            # 创建 mock 客户端
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            
            set_langfuse_trace_context(
                name="test_trace",
                user_id="user_123",
                session_id="session_456",
                metadata={"key": "value"}
            )
            
            mock_client.update_current_trace.assert_called_once_with(
                name="test_trace",
                user_id="user_123",
                session_id="session_456",
                metadata={"key": "value"}
            )
    
    def test_set_langfuse_trace_context_not_enabled(self):
        """测试 Langfuse 未启用时设置 Trace 上下文"""
        with patch.object(settings, 'LANGFUSE_ENABLED', False):
            # 不应该抛出异常，只是不执行
            set_langfuse_trace_context(
                name="test_trace",
                user_id="user_123"
            )
    
    def test_is_langfuse_available(self):
        """测试检查 Langfuse 是否可用"""
        # 测试 Langfuse 可用
        with patch('infrastructure.observability.langfuse_handler.LANGFUSE_AVAILABLE', True), \
             patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
             patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'):
            
            assert is_langfuse_available() is True
        
        # 测试 Langfuse 不可用（未启用）
        with patch('infrastructure.observability.langfuse_handler.LANGFUSE_AVAILABLE', True), \
             patch.object(settings, 'LANGFUSE_ENABLED', False):
            
            assert is_langfuse_available() is False
        
        # 测试 Langfuse 不可用（未安装）
        with patch('infrastructure.observability.langfuse_handler.LANGFUSE_AVAILABLE', False):
            assert is_langfuse_available() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

