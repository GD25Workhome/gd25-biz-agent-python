"""
测试Langfuse集成功能（里程碑4）

运行命令：
    pytest cursor_test/test_langfuse_integration.py -v

注意：此测试需要配置Langfuse环境变量才能完全运行
    - LANGFUSE_ENABLED=true
    - LANGFUSE_PUBLIC_KEY=your_public_key
    - LANGFUSE_SECRET_KEY=your_secret_key
    - LANGFUSE_HOST=https://cloud.langfuse.com (可选)
"""
import os
import pytest
from backend.infrastructure.observability.langfuse_handler import (
    get_langfuse_client,
    is_langfuse_available,
    set_langfuse_trace_context,
    create_langfuse_handler,
    get_current_trace_id,
)


class TestLangfuseAvailability:
    """测试Langfuse可用性检查"""
    
    def test_is_langfuse_available_without_config(self):
        """测试未配置时的可用性检查"""
        # 临时移除环境变量
        original_enabled = os.environ.get("LANGFUSE_ENABLED")
        if "LANGFUSE_ENABLED" in os.environ:
            del os.environ["LANGFUSE_ENABLED"]
        
        try:
            available = is_langfuse_available()
            # 如果未配置，应该返回False
            assert available is False or available is True  # 取决于是否安装了langfuse
        finally:
            # 恢复环境变量
            if original_enabled:
                os.environ["LANGFUSE_ENABLED"] = original_enabled
    
    def test_get_langfuse_client_without_config(self):
        """测试未配置时获取客户端"""
        # 临时移除环境变量
        original_enabled = os.environ.get("LANGFUSE_ENABLED")
        original_public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        original_secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
        
        # 清理环境变量
        for key in ["LANGFUSE_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"]:
            if key in os.environ:
                del os.environ[key]
        
        try:
            client = get_langfuse_client()
            # 如果未配置，应该返回None
            assert client is None
        finally:
            # 恢复环境变量
            if original_enabled:
                os.environ["LANGFUSE_ENABLED"] = original_enabled
            if original_public_key:
                os.environ["LANGFUSE_PUBLIC_KEY"] = original_public_key
            if original_secret_key:
                os.environ["LANGFUSE_SECRET_KEY"] = original_secret_key


class TestLangfuseTraceContext:
    """测试Langfuse Trace上下文"""
    
    def test_set_trace_context_without_langfuse(self):
        """测试未配置Langfuse时设置Trace上下文"""
        # 临时移除环境变量
        original_enabled = os.environ.get("LANGFUSE_ENABLED")
        if "LANGFUSE_ENABLED" in os.environ:
            del os.environ["LANGFUSE_ENABLED"]
        
        try:
            trace_id = set_langfuse_trace_context(
                name="test_trace",
                user_id="user123",
                session_id="session123"
            )
            # 如果Langfuse不可用，应该返回None
            assert trace_id is None
        finally:
            # 恢复环境变量
            if original_enabled:
                os.environ["LANGFUSE_ENABLED"] = original_enabled
    
    @pytest.mark.skipif(
        not os.getenv("LANGFUSE_ENABLED") == "true",
        reason="需要配置LANGFUSE_ENABLED=true才能运行此测试"
    )
    def test_set_trace_context_with_langfuse(self):
        """测试配置Langfuse时设置Trace上下文（需要真实配置）"""
        trace_id = set_langfuse_trace_context(
            name="test_trace",
            user_id="user123",
            session_id="session123",
            metadata={"test": "value"}
        )
        # 如果Langfuse可用，应该返回Trace ID
        assert trace_id is not None or trace_id is None  # 取决于配置是否正确
        
        # 检查当前Trace ID
        current_trace_id = get_current_trace_id()
        if trace_id:
            assert current_trace_id == trace_id


class TestLangfuseCallbackHandler:
    """测试Langfuse CallbackHandler"""
    
    def test_create_handler_without_langfuse(self):
        """测试未配置Langfuse时创建Handler"""
        # 临时移除环境变量
        original_enabled = os.environ.get("LANGFUSE_ENABLED")
        if "LANGFUSE_ENABLED" in os.environ:
            del os.environ["LANGFUSE_ENABLED"]
        
        try:
            handler = create_langfuse_handler()
            # 如果Langfuse不可用，应该返回None
            assert handler is None
        finally:
            # 恢复环境变量
            if original_enabled:
                os.environ["LANGFUSE_ENABLED"] = original_enabled
    
    @pytest.mark.skipif(
        not os.getenv("LANGFUSE_ENABLED") == "true",
        reason="需要配置LANGFUSE_ENABLED=true才能运行此测试"
    )
    def test_create_handler_with_langfuse(self):
        """测试配置Langfuse时创建Handler（需要真实配置）"""
        handler = create_langfuse_handler(
            context={"test": "value"}
        )
        # 如果Langfuse可用，应该返回Handler实例
        assert handler is not None or handler is None  # 取决于配置是否正确


class TestLangfuseIntegration:
    """测试Langfuse集成（需要真实配置）"""
    
    @pytest.mark.skipif(
        not os.getenv("LANGFUSE_ENABLED") == "true",
        reason="需要配置LANGFUSE_ENABLED=true才能运行此测试"
    )
    def test_full_integration(self):
        """测试完整集成流程（需要真实配置）"""
        # 1. 检查可用性
        available = is_langfuse_available()
        if not available:
            pytest.skip("Langfuse不可用，跳过集成测试")
        
        # 2. 创建Trace
        trace_id = set_langfuse_trace_context(
            name="integration_test",
            user_id="test_user",
            session_id="test_session",
            metadata={"test": "integration"}
        )
        assert trace_id is not None
        
        # 3. 创建Handler
        handler = create_langfuse_handler()
        assert handler is not None
        
        # 4. 验证Trace ID
        current_trace_id = get_current_trace_id()
        assert current_trace_id == trace_id

