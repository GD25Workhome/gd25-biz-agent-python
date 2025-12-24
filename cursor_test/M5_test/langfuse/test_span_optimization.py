"""
测试 Span 创建性能优化
验证元数据优化、错误隔离和条件创建机制
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage

from app.core.config import settings
from domain.router.node import route_node, clarify_intent_node
from domain.router.state import RouterState


class TestSpanMetadataOptimization:
    """测试 Span 元数据优化（里程碑三）"""
    
    def test_route_node_metadata_optimization(self):
        """测试路由节点元数据优化（移除冗余的 session_id 和 user_id）"""
        # 创建 mock Langfuse 客户端
        mock_langfuse_client = MagicMock()
        mock_span_context = MagicMock()
        mock_langfuse_client.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span_context)
        mock_langfuse_client.start_as_current_span.return_value.__exit__ = Mock(return_value=False)
        
        # 创建测试状态
        state: RouterState = {
            "messages": [HumanMessage(content="我想记录血压")],
            "current_intent": None,
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_123",
            "user_id": "test_user_456",
            "trace_id": "test_trace_789",
        }
        
        with patch('domain.router.node.get_langfuse_client', return_value=mock_langfuse_client), \
             patch('domain.router.node.settings.LANGFUSE_ENABLED', True), \
             patch('domain.router.node.settings.LANGFUSE_ENABLE_SPANS', True), \
             patch('domain.router.node.identify_intent') as mock_identify_intent:
            
            # Mock 意图识别结果
            mock_identify_intent.invoke.return_value = {
                "intent_type": "blood_pressure",
                "confidence": 0.9,
                "need_clarification": False,
            }
            
            # 执行路由节点
            result = route_node(state)
            
            # 验证 Span 被创建
            assert mock_langfuse_client.start_as_current_span.called
            
            # 获取调用参数
            call_args = mock_langfuse_client.start_as_current_span.call_args
            span_params = call_args.kwargs
            
            # 验证元数据优化：
            # 1. metadata 中不应包含 session_id 和 user_id（已在 Trace 级别设置）
            metadata = span_params.get("metadata", {})
            assert "session_id" not in metadata, "metadata 中不应包含 session_id"
            assert "user_id" not in metadata, "metadata 中不应包含 user_id"
            
            # 2. input 中应包含路由相关的信息
            input_data = span_params.get("input", {})
            assert "messages_count" in input_data
            assert "current_intent" in input_data
            assert "current_agent" in input_data
    
    def test_clarify_intent_node_metadata_optimization(self):
        """测试澄清节点元数据优化（移除冗余的 session_id 和 user_id）"""
        # 创建 mock Langfuse 客户端
        mock_langfuse_client = MagicMock()
        mock_span_context = MagicMock()
        mock_langfuse_client.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span_context)
        mock_langfuse_client.start_as_current_span.return_value.__exit__ = Mock(return_value=False)
        
        # 创建测试状态
        state: RouterState = {
            "messages": [HumanMessage(content="你好")],
            "current_intent": "unclear",
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_123",
            "user_id": "test_user_456",
            "trace_id": "test_trace_789",
        }
        
        with patch('domain.router.node.get_langfuse_client', return_value=mock_langfuse_client), \
             patch('domain.router.node.settings.LANGFUSE_ENABLED', True), \
             patch('domain.router.node.settings.LANGFUSE_ENABLE_SPANS', True), \
             patch('domain.router.node.clarify_intent') as mock_clarify_intent:
            
            # Mock 澄清结果
            mock_clarify_intent.invoke.return_value = "请告诉我您的具体需求"
            
            # 执行澄清节点
            result = clarify_intent_node(state)
            
            # 验证 Span 被创建
            assert mock_langfuse_client.start_as_current_span.called
            
            # 获取调用参数
            call_args = mock_langfuse_client.start_as_current_span.call_args
            span_params = call_args.kwargs
            
            # 验证元数据优化：
            # metadata 中不应包含 session_id 和 user_id
            metadata = span_params.get("metadata", {})
            assert "session_id" not in metadata, "metadata 中不应包含 session_id"
            assert "user_id" not in metadata, "metadata 中不应包含 user_id"
    
    def test_agent_node_metadata_optimization(self):
        """测试 Agent 节点元数据优化（移除冗余的 session_id、user_id 和 agent_key）"""
        # 这个测试需要集成测试，因为需要实际的路由图
        # 这里只验证元数据优化的概念
        pass


class TestSpanErrorIsolation:
    """测试 Span 创建错误隔离（里程碑四）"""
    
    def test_route_node_span_error_isolation(self):
        """测试路由节点 Span 创建失败时的错误隔离"""
        # 创建 mock Langfuse 客户端，模拟 Span 创建失败
        mock_langfuse_client = MagicMock()
        mock_langfuse_client.start_as_current_span.side_effect = Exception("Span 创建失败")
        
        # 创建测试状态
        state: RouterState = {
            "messages": [HumanMessage(content="我想记录血压")],
            "current_intent": None,
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_123",
            "user_id": "test_user_456",
            "trace_id": "test_trace_789",
        }
        
        with patch('domain.router.node.get_langfuse_client', return_value=mock_langfuse_client), \
             patch('domain.router.node.settings.LANGFUSE_ENABLED', True), \
             patch('domain.router.node.settings.LANGFUSE_ENABLE_SPANS', True), \
             patch('domain.router.node.identify_intent') as mock_identify_intent:
            
            # Mock 意图识别结果
            mock_identify_intent.invoke.return_value = {
                "intent_type": "blood_pressure",
                "confidence": 0.9,
                "need_clarification": False,
            }
            
            # 执行路由节点应该不抛出异常，而是继续执行主流程
            result = route_node(state)
            
            # 验证主流程正常执行（状态已更新）
            assert result is not None
            assert "current_intent" in result
    
    def test_clarify_intent_node_span_error_isolation(self):
        """测试澄清节点 Span 创建失败时的错误隔离"""
        # 创建 mock Langfuse 客户端，模拟 Span 创建失败
        mock_langfuse_client = MagicMock()
        mock_langfuse_client.start_as_current_span.side_effect = Exception("Span 创建失败")
        
        # 创建测试状态
        state: RouterState = {
            "messages": [HumanMessage(content="你好")],
            "current_intent": "unclear",
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_123",
            "user_id": "test_user_456",
            "trace_id": "test_trace_789",
        }
        
        with patch('domain.router.node.get_langfuse_client', return_value=mock_langfuse_client), \
             patch('domain.router.node.settings.LANGFUSE_ENABLED', True), \
             patch('domain.router.node.settings.LANGFUSE_ENABLE_SPANS', True), \
             patch('domain.router.node.clarify_intent') as mock_clarify_intent:
            
            # Mock 澄清结果
            mock_clarify_intent.invoke.return_value = "请告诉我您的具体需求"
            
            # 执行澄清节点应该不抛出异常，而是继续执行主流程
            result = clarify_intent_node(state)
            
            # 验证主流程正常执行
            assert result is not None
            assert "messages" in result


class TestSpanConditionalCreation:
    """测试 Span 条件创建（里程碑四）"""
    
    def test_route_node_span_disabled(self):
        """测试禁用 Span 创建时，路由节点不创建 Span"""
        # 创建 mock Langfuse 客户端
        mock_langfuse_client = MagicMock()
        
        # 创建测试状态
        state: RouterState = {
            "messages": [HumanMessage(content="我想记录血压")],
            "current_intent": None,
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_123",
            "user_id": "test_user_456",
            "trace_id": "test_trace_789",
        }
        
        with patch('domain.router.node.get_langfuse_client', return_value=mock_langfuse_client), \
             patch('domain.router.node.settings.LANGFUSE_ENABLED', True), \
             patch('domain.router.node.settings.LANGFUSE_ENABLE_SPANS', False), \
             patch('domain.router.node.identify_intent') as mock_identify_intent:
            
            # Mock 意图识别结果
            mock_identify_intent.invoke.return_value = {
                "intent_type": "blood_pressure",
                "confidence": 0.9,
                "need_clarification": False,
            }
            
            # 执行路由节点
            result = route_node(state)
            
            # 验证 Span 未被创建（因为 LANGFUSE_ENABLE_SPANS=False）
            assert not mock_langfuse_client.start_as_current_span.called
            
            # 验证主流程正常执行
            assert result is not None
    
    def test_clarify_intent_node_span_disabled(self):
        """测试禁用 Span 创建时，澄清节点不创建 Span"""
        # 创建 mock Langfuse 客户端
        mock_langfuse_client = MagicMock()
        
        # 创建测试状态
        state: RouterState = {
            "messages": [HumanMessage(content="你好")],
            "current_intent": "unclear",
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_123",
            "user_id": "test_user_456",
            "trace_id": "test_trace_789",
        }
        
        with patch('domain.router.node.get_langfuse_client', return_value=mock_langfuse_client), \
             patch('domain.router.node.settings.LANGFUSE_ENABLED', True), \
             patch('domain.router.node.settings.LANGFUSE_ENABLE_SPANS', False), \
             patch('domain.router.node.clarify_intent') as mock_clarify_intent:
            
            # Mock 澄清结果
            mock_clarify_intent.invoke.return_value = "请告诉我您的具体需求"
            
            # 执行澄清节点
            result = clarify_intent_node(state)
            
            # 验证 Span 未被创建
            assert not mock_langfuse_client.start_as_current_span.called
            
            # 验证主流程正常执行
            assert result is not None
    
    def test_span_creation_when_langfuse_disabled(self):
        """测试 Langfuse 未启用时，不创建 Span"""
        # 创建测试状态
        state: RouterState = {
            "messages": [HumanMessage(content="我想记录血压")],
            "current_intent": None,
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_123",
            "user_id": "test_user_456",
            "trace_id": "test_trace_789",
        }
        
        with patch('domain.router.node.get_langfuse_client', return_value=None), \
             patch('domain.router.node.settings.LANGFUSE_ENABLED', False), \
             patch('domain.router.node.settings.LANGFUSE_ENABLE_SPANS', True), \
             patch('domain.router.node.identify_intent') as mock_identify_intent:
            
            # Mock 意图识别结果
            mock_identify_intent.invoke.return_value = {
                "intent_type": "blood_pressure",
                "confidence": 0.9,
                "need_clarification": False,
            }
            
            # 执行路由节点应该不抛出异常
            result = route_node(state)
            
            # 验证主流程正常执行
            assert result is not None


class TestConfigValidation:
    """测试配置验证"""
    
    def test_langfuse_enable_spans_config_loading(self):
        """测试 LANGFUSE_ENABLE_SPANS 配置加载"""
        # 验证配置项存在
        assert hasattr(settings, 'LANGFUSE_ENABLE_SPANS')
        
        # 验证默认值
        assert settings.LANGFUSE_ENABLE_SPANS is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

