"""
测试 Langfuse Span 追踪功能
验证路由节点和路由图节点中的 Span 追踪是否正确集成
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage

from app.core.config import settings
from domain.router.state import RouterState
from domain.router.node import route_node, clarify_intent_node
from infrastructure.observability.langfuse_handler import get_langfuse_client


class TestSpanTracking:
    """测试 Span 追踪功能"""
    
    def test_get_langfuse_client_enabled(self):
        """测试获取 Langfuse 客户端（启用时）"""
        try:
            from langfuse import Langfuse
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        with patch('infrastructure.observability.langfuse_handler.is_langfuse_available', return_value=True), \
             patch('infrastructure.observability.langfuse_handler._get_langfuse_client') as mock_get_client:
            
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            
            client = get_langfuse_client()
            assert client is not None
            assert client == mock_client
    
    def test_get_langfuse_client_disabled(self):
        """测试获取 Langfuse 客户端（禁用时）"""
        with patch('infrastructure.observability.langfuse_handler.is_langfuse_available', return_value=False):
            client = get_langfuse_client()
            assert client is None
    
    def test_route_node_with_span_tracking(self):
        """测试路由节点中的 Span 追踪"""
        try:
            from langfuse import Langfuse
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        # 模拟状态
        state: RouterState = {
            "messages": [HumanMessage(content="我想记录血压")],
            "current_intent": None,
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session",
            "user_id": "test_user"
        }
        
        # 模拟意图识别工具
        mock_intent_result = {
            "intent_type": "blood_pressure",
            "confidence": 0.9,
            "entities": {},
            "need_clarification": False
        }
        
        with patch('domain.router.node.identify_intent') as mock_identify_intent, \
             patch('domain.router.node.AgentRegistry') as mock_agent_registry, \
             patch('domain.router.node.get_langfuse_client') as mock_get_client, \
             patch('domain.router.node.logger'):
            
            # 模拟 AgentRegistry
            mock_agent_registry.get_all_agents.return_value = {
                "blood_pressure_agent": {
                    "routing": {"intent_type": "blood_pressure"}
                }
            }
            
            # 模拟 Langfuse 客户端
            mock_span = MagicMock()
            mock_span.__enter__ = Mock(return_value=mock_span)
            mock_span.__exit__ = Mock(return_value=False)
            mock_client = MagicMock()
            mock_client.start_as_current_span = Mock(return_value=mock_span)
            mock_get_client.return_value = mock_client
            
            # 模拟意图识别
            mock_identify_intent.invoke = Mock(return_value=mock_intent_result)
            
            # 执行路由节点
            result = route_node(state)
            
            # 验证 Span 被创建
            mock_client.start_as_current_span.assert_called_once()
            call_args = mock_client.start_as_current_span.call_args
            assert call_args[1]["name"] == "route_node"
            assert "messages_count" in call_args[1]["input"]
            assert "session_id" in call_args[1]["metadata"]
            
            # 验证状态更新
            assert result["current_intent"] == "blood_pressure"
            assert result["need_reroute"] is True
    
    def test_route_node_without_span_tracking(self):
        """测试路由节点（Langfuse 未启用时）"""
        # 模拟状态
        state: RouterState = {
            "messages": [HumanMessage(content="我想记录血压")],
            "current_intent": None,
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session",
            "user_id": "test_user"
        }
        
        # 模拟意图识别工具
        mock_intent_result = {
            "intent_type": "blood_pressure",
            "confidence": 0.9,
            "entities": {},
            "need_clarification": False
        }
        
        with patch('domain.router.node.identify_intent') as mock_identify_intent, \
             patch('domain.router.node.get_langfuse_client', return_value=None), \
             patch('domain.router.node.logger'):
            
            # 模拟意图识别
            mock_identify_intent.invoke = Mock(return_value=mock_intent_result)
            
            # 执行路由节点
            result = route_node(state)
            
            # 验证状态更新（即使没有 Span 追踪，功能也应该正常）
            assert result["current_intent"] == "blood_pressure"
            assert result["need_reroute"] is True
    
    def test_clarify_intent_node_with_span_tracking(self):
        """测试澄清节点中的 Span 追踪"""
        try:
            from langfuse import Langfuse
        except ImportError:
            pytest.skip("Langfuse未安装，跳过测试")
        
        # 模拟状态
        state: RouterState = {
            "messages": [HumanMessage(content="你好")],
            "current_intent": "unclear",
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session",
            "user_id": "test_user"
        }
        
        # 模拟澄清工具
        mock_clarification = "请告诉我您是想记录血压、预约复诊，还是需要其他帮助？"
        
        with patch('domain.router.node.clarify_intent') as mock_clarify_intent, \
             patch('domain.router.node.get_langfuse_client') as mock_get_client, \
             patch('domain.router.node.logger'):
            
            # 模拟 Langfuse 客户端
            mock_span = MagicMock()
            mock_span.__enter__ = Mock(return_value=mock_span)
            mock_span.__exit__ = Mock(return_value=False)
            mock_client = MagicMock()
            mock_client.start_as_current_span = Mock(return_value=mock_span)
            mock_get_client.return_value = mock_client
            
            # 模拟澄清工具
            mock_clarify_intent.invoke = Mock(return_value=mock_clarification)
            
            # 执行澄清节点
            result = clarify_intent_node(state)
            
            # 验证 Span 被创建
            mock_client.start_as_current_span.assert_called_once()
            call_args = mock_client.start_as_current_span.call_args
            assert call_args[1]["name"] == "clarify_intent_node"
            assert "user_query" in call_args[1]["input"]
            assert "session_id" in call_args[1]["metadata"]
            
            # 验证状态更新
            assert len(result["messages"]) == 2
            assert isinstance(result["messages"][-1], AIMessage)
            assert result["need_reroute"] is True
    
    def test_clarify_intent_node_without_span_tracking(self):
        """测试澄清节点（Langfuse 未启用时）"""
        # 模拟状态
        state: RouterState = {
            "messages": [HumanMessage(content="你好")],
            "current_intent": "unclear",
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session",
            "user_id": "test_user"
        }
        
        # 模拟澄清工具
        mock_clarification = "请告诉我您是想记录血压、预约复诊，还是需要其他帮助？"
        
        with patch('domain.router.node.clarify_intent') as mock_clarify_intent, \
             patch('domain.router.node.get_langfuse_client', return_value=None), \
             patch('domain.router.node.logger'):
            
            # 模拟澄清工具
            mock_clarify_intent.invoke = Mock(return_value=mock_clarification)
            
            # 执行澄清节点
            result = clarify_intent_node(state)
            
            # 验证状态更新（即使没有 Span 追踪，功能也应该正常）
            assert len(result["messages"]) == 2
            assert isinstance(result["messages"][-1], AIMessage)
            assert result["need_reroute"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

