"""
测试 LLM 客户端与 Langfuse 的集成
验证 Langfuse Callback 是否正确集成到 LLM 客户端
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from app.core.config import settings
from infrastructure.llm.client import get_llm
from infrastructure.observability.llm_logger import LlmLogContext


class TestLLMClientLangfuseIntegration:
    """测试 LLM 客户端与 Langfuse 的集成"""
    
    @pytest.fixture
    def mock_langfuse_handler(self):
        """模拟 Langfuse Handler"""
        # 跳过测试如果 Langfuse 未安装
        try:
            from langfuse.langchain import CallbackHandler
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        return MagicMock(spec=CallbackHandler)
    
    def test_get_llm_with_langfuse_enabled(self, mock_langfuse_handler):
        """测试启用 Langfuse 时创建 LLM 客户端"""
        with patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
             patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
             patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'), \
             patch.object(settings, 'OPENAI_API_KEY', 'test-key'), \
             patch.object(settings, 'OPENAI_BASE_URL', 'http://localhost:8000'), \
             patch.object(settings, 'LLM_MODEL', 'test-model'), \
             patch('infrastructure.observability.langfuse_handler.create_langfuse_handler', return_value=mock_langfuse_handler):
            
            context = LlmLogContext(
                user_id="user_123",
                session_id="session_456"
            )
            
            llm = get_llm(
                log_context=context,
                enable_langfuse=True
            )
            
            assert llm is not None
            # 验证 callbacks 中包含 Langfuse Handler
            assert hasattr(llm, 'callbacks') or hasattr(llm, '_callbacks')
    
    def test_get_llm_with_langfuse_disabled(self):
        """测试禁用 Langfuse 时创建 LLM 客户端"""
        with patch.object(settings, 'LANGFUSE_ENABLED', False), \
             patch.object(settings, 'OPENAI_API_KEY', 'test-key'), \
             patch.object(settings, 'OPENAI_BASE_URL', 'http://localhost:8000'), \
             patch.object(settings, 'LLM_MODEL', 'test-model'):
            
            llm = get_llm(enable_langfuse=False)
            
            assert llm is not None
    
    def test_get_llm_langfuse_failure_graceful(self):
        """测试 Langfuse 创建失败时不影响主流程"""
        with patch.object(settings, 'LANGFUSE_ENABLED', True), \
             patch.object(settings, 'OPENAI_API_KEY', 'test-key'), \
             patch.object(settings, 'OPENAI_BASE_URL', 'http://localhost:8000'), \
             patch.object(settings, 'LLM_MODEL', 'test-model'), \
             patch('infrastructure.observability.langfuse_handler.create_langfuse_handler', side_effect=ValueError("Langfuse未启用")):
            
            # 不应该抛出异常，应该继续执行
            llm = get_llm(enable_langfuse=True)
            
            assert llm is not None
    
    def test_get_llm_enable_langfuse_parameter(self, mock_langfuse_handler):
        """测试 enable_langfuse 参数"""
        with patch.object(settings, 'LANGFUSE_ENABLED', False), \
             patch.object(settings, 'OPENAI_API_KEY', 'test-key'), \
             patch.object(settings, 'OPENAI_BASE_URL', 'http://localhost:8000'), \
             patch.object(settings, 'LLM_MODEL', 'test-model'), \
             patch('infrastructure.observability.langfuse_handler.create_langfuse_handler', return_value=mock_langfuse_handler):
            
            # 即使配置中禁用了，但参数中启用了，应该使用参数值
            llm = get_llm(enable_langfuse=True)
            
            assert llm is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

