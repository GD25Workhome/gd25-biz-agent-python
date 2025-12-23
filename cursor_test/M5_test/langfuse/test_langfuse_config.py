"""
测试 Langfuse SDK 配置调优
验证性能配置项和错误隔离机制
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from app.core.config import settings
from infrastructure.observability.langfuse_handler import (
    get_langfuse_client,
    _get_langfuse_client,
    set_langfuse_trace_context,
)


class TestLangfuseConfig:
    """测试 Langfuse 配置"""
    
    def test_langfuse_config_loading(self):
        """测试 Langfuse 配置加载"""
        # 验证配置项存在且有默认值
        assert hasattr(settings, 'LANGFUSE_FLUSH_AT')
        assert hasattr(settings, 'LANGFUSE_FLUSH_INTERVAL')
        assert hasattr(settings, 'LANGFUSE_TIMEOUT')
        assert hasattr(settings, 'LANGFUSE_DEBUG')
        assert hasattr(settings, 'LANGFUSE_TRACING_ENABLED')
        
        # 验证默认值
        assert settings.LANGFUSE_FLUSH_AT == 20
        assert settings.LANGFUSE_FLUSH_INTERVAL == 5.0
        assert settings.LANGFUSE_TIMEOUT == 2
        assert settings.LANGFUSE_DEBUG is False
        assert settings.LANGFUSE_TRACING_ENABLED is True
    
    def test_langfuse_client_initialization_with_config(self):
        """测试 Langfuse 客户端初始化（带性能配置）"""
        try:
            from langfuse import Langfuse
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        # 重置全局客户端
        import infrastructure.observability.langfuse_handler as langfuse_module
        langfuse_module._langfuse_client = None
        
        with patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
             patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
             patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'), \
             patch.object(settings, 'LANGFUSE_FLUSH_AT', 20), \
             patch.object(settings, 'LANGFUSE_FLUSH_INTERVAL', 5.0), \
             patch.object(settings, 'LANGFUSE_TIMEOUT', 2), \
             patch.object(settings, 'LANGFUSE_DEBUG', False), \
             patch.object(settings, 'LANGFUSE_TRACING_ENABLED', True), \
             patch('infrastructure.observability.langfuse_handler.Langfuse') as mock_langfuse_class:
            
            # 创建 mock 客户端实例
            mock_client = MagicMock()
            mock_langfuse_class.return_value = mock_client
            
            # 获取客户端
            client = get_langfuse_client()
            
            # 验证客户端已创建
            assert client is not None
            
            # 验证 Langfuse 构造函数被调用，且传入了性能配置参数
            mock_langfuse_class.assert_called_once()
            call_kwargs = mock_langfuse_class.call_args[1]  # 获取关键字参数
            
            # 验证性能配置参数已传入
            assert call_kwargs.get('flush_at') == 20
            assert call_kwargs.get('flush_interval') == 5.0
            assert call_kwargs.get('timeout') == 2
            assert call_kwargs.get('debug') is False
            assert call_kwargs.get('tracing_enabled') is True
    
    def test_langfuse_client_initialization_with_custom_config(self):
        """测试 Langfuse 客户端初始化（自定义配置）"""
        try:
            from langfuse import Langfuse
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        # 重置全局客户端
        import infrastructure.observability.langfuse_handler as langfuse_module
        langfuse_module._langfuse_client = None
        
        with patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
             patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
             patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'), \
             patch.object(settings, 'LANGFUSE_FLUSH_AT', 50), \
             patch.object(settings, 'LANGFUSE_FLUSH_INTERVAL', 10.0), \
             patch.object(settings, 'LANGFUSE_TIMEOUT', 5), \
             patch.object(settings, 'LANGFUSE_DEBUG', True), \
             patch.object(settings, 'LANGFUSE_TRACING_ENABLED', False), \
             patch('infrastructure.observability.langfuse_handler.Langfuse') as mock_langfuse_class:
            
            # 创建 mock 客户端实例
            mock_client = MagicMock()
            mock_langfuse_class.return_value = mock_client
            
            # 获取客户端
            client = get_langfuse_client()
            
            # 验证客户端已创建
            assert client is not None
            
            # 验证自定义配置参数已传入
            call_kwargs = mock_langfuse_class.call_args[1]
            assert call_kwargs.get('flush_at') == 50
            assert call_kwargs.get('flush_interval') == 10.0
            assert call_kwargs.get('timeout') == 5
            assert call_kwargs.get('debug') is True
            assert call_kwargs.get('tracing_enabled') is False
    
    def test_langfuse_client_initialization_error_isolation(self):
        """测试 Langfuse 客户端初始化错误隔离"""
        try:
            from langfuse import Langfuse
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        # 重置全局客户端
        import infrastructure.observability.langfuse_handler as langfuse_module
        langfuse_module._langfuse_client = None
        
        with patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
             patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
             patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'), \
             patch('infrastructure.observability.langfuse_handler.Langfuse') as mock_langfuse_class:
            
            # 模拟初始化失败
            mock_langfuse_class.side_effect = Exception("初始化失败")
            
            # 获取客户端应该返回 None，而不是抛出异常
            client = get_langfuse_client()
            assert client is None
            
            # 验证 Langfuse 构造函数被调用
            mock_langfuse_class.assert_called_once()
    
    def test_set_langfuse_trace_context_error_isolation(self):
        """测试设置 Trace 上下文错误隔离"""
        try:
            from langfuse import Langfuse
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        with patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
             patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
             patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'), \
             patch('infrastructure.observability.langfuse_handler._get_langfuse_client') as mock_get_client:
            
            # 创建 mock 客户端，模拟 update_current_trace 失败
            mock_client = MagicMock()
            mock_client.update_current_trace.side_effect = Exception("网络错误")
            mock_get_client.return_value = mock_client
            
            # 设置 Trace 上下文应该不抛出异常，而是返回 trace_id
            trace_id = set_langfuse_trace_context(
                name="test_trace",
                user_id="user_123",
                session_id="session_456",
                trace_id="trace_789"
            )
            
            # 验证返回了 trace_id（即使操作失败）
            assert trace_id == "trace_789"
            
            # 验证 update_current_trace 被调用
            mock_client.update_current_trace.assert_called()
    
    def test_set_langfuse_trace_context_with_client_none(self):
        """测试客户端为 None 时的错误隔离"""
        with patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
             patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
             patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'), \
             patch('infrastructure.observability.langfuse_handler._get_langfuse_client') as mock_get_client:
            
            # 模拟客户端为 None
            mock_get_client.return_value = None
            
            # 设置 Trace 上下文应该不抛出异常
            trace_id = set_langfuse_trace_context(
                name="test_trace",
                user_id="user_123",
                trace_id="trace_789"
            )
            
            # 验证返回了 trace_id
            assert trace_id == "trace_789"
    
    def test_langfuse_client_singleton(self):
        """测试 Langfuse 客户端单例模式"""
        try:
            from langfuse import Langfuse
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        # 重置全局客户端
        import infrastructure.observability.langfuse_handler as langfuse_module
        langfuse_module._langfuse_client = None
        
        with patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
             patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
             patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'), \
             patch('infrastructure.observability.langfuse_handler.Langfuse') as mock_langfuse_class:
            
            # 创建 mock 客户端实例
            mock_client = MagicMock()
            mock_langfuse_class.return_value = mock_client
            
            # 第一次获取客户端
            client1 = get_langfuse_client()
            
            # 第二次获取客户端（应该返回同一个实例）
            client2 = get_langfuse_client()
            
            # 验证是同一个实例
            assert client1 is client2
            
            # 验证 Langfuse 构造函数只被调用一次（单例模式）
            assert mock_langfuse_class.call_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

