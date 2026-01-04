"""
工具调用 Langfuse Span 测试

Pytest 命令示例：
================

# 运行整个测试文件
pytest cursor_test/tools/test_tool_langfuse_span.py

# 运行整个测试文件（详细输出）
pytest cursor_test/tools/test_tool_langfuse_span.py -v

# 运行整个测试文件（显示 print 输出）
pytest cursor_test/tools/test_tool_langfuse_span.py -s

# 运行特定的测试方法
pytest cursor_test/tools/test_tool_langfuse_span.py::TestToolLangfuseSpan::test_tool_span_creation
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from langchain_core.tools import BaseTool, tool
from langchain_core.messages import ToolMessage

from domain.tools.wrapper import TokenInjectedTool
from domain.tools.context import TokenContext
from app.core.config import settings


# 创建一个简单的测试工具
@tool
async def test_async_tool(token_id: str, param1: str) -> str:
    """异步测试工具"""
    return f"token_id={token_id}, param1={param1}"


@tool
async def test_async_tool_with_error(token_id: str) -> str:
    """会抛出错误的测试工具"""
    raise ValueError("测试错误")


class TestToolLangfuseSpan:
    """工具调用 Langfuse Span 测试类"""
    
    @pytest.mark.asyncio
    async def test_tool_span_creation_when_enabled(self):
        """测试工具执行时是否创建 Langfuse Span（Langfuse 启用时）"""
        # Arrange
        original_tool = test_async_tool
        wrapped_tool = TokenInjectedTool(tool=original_tool)
        token_id = "test_token_123"
        
        # Mock Langfuse 客户端
        mock_span_context = MagicMock()
        mock_span_context.__enter__ = MagicMock(return_value=mock_span_context)
        mock_span_context.__exit__ = MagicMock(return_value=False)
        
        mock_langfuse_client = MagicMock()
        mock_langfuse_client.start_as_current_span = MagicMock(return_value=mock_span_context)
        
        with patch('domain.tools.wrapper.get_langfuse_client', return_value=mock_langfuse_client):
            with patch.object(settings, 'LANGFUSE_ENABLED', True):
                with patch.object(settings, 'LANGFUSE_ENABLE_SPANS', True):
                    # Act
                    with TokenContext(token_id=token_id):
                        result = await wrapped_tool.ainvoke({"param1": "value1"})
                    
                    # Assert
                    # 验证 Span 被创建
                    assert mock_langfuse_client.start_as_current_span.called
                    call_args = mock_langfuse_client.start_as_current_span.call_args
                    assert call_args is not None
                    
                    # 验证 Span 参数
                    span_kwargs = call_args.kwargs
                    assert span_kwargs['name'] == f"tool_{original_tool.name}"
                    assert 'tool_name' in span_kwargs['input']
                    assert span_kwargs['input']['tool_name'] == original_tool.name
                    assert 'tool_input' in span_kwargs['input']
                    assert span_kwargs['input']['tool_input']['param1'] == "value1"
                    assert 'metadata' in span_kwargs
                    
                    # 验证工具执行成功
                    assert "token_id=test_token_123" in result
                    assert "param1=value1" in result
    
    @pytest.mark.asyncio
    async def test_tool_span_not_created_when_disabled(self):
        """测试 Langfuse 未启用时不创建 Span"""
        # Arrange
        original_tool = test_async_tool
        wrapped_tool = TokenInjectedTool(tool=original_tool)
        token_id = "test_token_123"
        
        mock_langfuse_client = MagicMock()
        
        with patch('domain.tools.wrapper.get_langfuse_client', return_value=mock_langfuse_client):
            with patch.object(settings, 'LANGFUSE_ENABLED', False):
                # Act
                with TokenContext(token_id=token_id):
                    result = await wrapped_tool.ainvoke({"param1": "value1"})
                
                # Assert
                # 验证 Span 未被创建
                assert not mock_langfuse_client.start_as_current_span.called
                
                # 验证工具执行成功
                assert "token_id=test_token_123" in result
    
    @pytest.mark.asyncio
    async def test_tool_span_not_created_when_spans_disabled(self):
        """测试 Span 追踪未启用时不创建 Span"""
        # Arrange
        original_tool = test_async_tool
        wrapped_tool = TokenInjectedTool(tool=original_tool)
        token_id = "test_token_123"
        
        mock_langfuse_client = MagicMock()
        
        with patch('domain.tools.wrapper.get_langfuse_client', return_value=mock_langfuse_client):
            with patch.object(settings, 'LANGFUSE_ENABLED', True):
                with patch.object(settings, 'LANGFUSE_ENABLE_SPANS', False):
                    # Act
                    with TokenContext(token_id=token_id):
                        result = await wrapped_tool.ainvoke({"param1": "value1"})
                    
                    # Assert
                    # 验证 Span 未被创建
                    assert not mock_langfuse_client.start_as_current_span.called
                    
                    # 验证工具执行成功
                    assert "token_id=test_token_123" in result
    
    @pytest.mark.asyncio
    async def test_tool_span_with_langchain_format(self):
        """测试 LangChain 工具调用格式（包含 'args' 字段）"""
        # Arrange
        original_tool = test_async_tool
        wrapped_tool = TokenInjectedTool(tool=original_tool)
        token_id = "test_token_123"
        
        # LangChain 工具调用格式
        tool_input = {
            "name": original_tool.name,
            "args": {"param1": "value1"},
            "id": "call_123",
            "type": "tool_call"
        }
        
        mock_span_context = MagicMock()
        mock_span_context.__enter__ = MagicMock(return_value=mock_span_context)
        mock_span_context.__exit__ = MagicMock(return_value=False)
        
        mock_langfuse_client = MagicMock()
        mock_langfuse_client.start_as_current_span = MagicMock(return_value=mock_span_context)
        
        with patch('domain.tools.wrapper.get_langfuse_client', return_value=mock_langfuse_client):
            with patch.object(settings, 'LANGFUSE_ENABLED', True):
                with patch.object(settings, 'LANGFUSE_ENABLE_SPANS', True):
                    # Act
                    with TokenContext(token_id=token_id):
                        result = await wrapped_tool.ainvoke(tool_input)
                    
                    # Assert
                    # 验证 Span 被创建
                    assert mock_langfuse_client.start_as_current_span.called
                    call_args = mock_langfuse_client.start_as_current_span.call_args
                    span_kwargs = call_args.kwargs
                    
                    # 验证 Span 输入参数（应该从 'args' 中提取）
                    assert 'tool_input' in span_kwargs['input']
                    assert span_kwargs['input']['tool_input']['param1'] == "value1"
                    
                    # 验证 metadata 中包含 tool_call_id
                    assert 'tool_call_id' in span_kwargs['metadata']
                    assert span_kwargs['metadata']['tool_call_id'] == "call_123"
                    
                    # 验证返回 ToolMessage（因为 tool_input 包含 'id'）
                    assert isinstance(result, ToolMessage)
                    assert result.tool_call_id == "call_123"
    
    @pytest.mark.asyncio
    async def test_tool_span_error_handling(self):
        """测试工具执行失败时错误信息是否正确记录"""
        # Arrange
        original_tool = test_async_tool_with_error
        wrapped_tool = TokenInjectedTool(tool=original_tool)
        token_id = "test_token_123"
        
        mock_span_context = MagicMock()
        mock_span_context.__enter__ = MagicMock(return_value=mock_span_context)
        mock_span_context.__exit__ = MagicMock(return_value=False)
        
        mock_langfuse_client = MagicMock()
        mock_langfuse_client.start_as_current_span = MagicMock(return_value=mock_span_context)
        
        with patch('domain.tools.wrapper.get_langfuse_client', return_value=mock_langfuse_client):
            with patch.object(settings, 'LANGFUSE_ENABLED', True):
                with patch.object(settings, 'LANGFUSE_ENABLE_SPANS', True):
                    # Act & Assert
                    with TokenContext(token_id=token_id):
                        # 验证工具执行失败
                        with pytest.raises(ValueError, match="测试错误"):
                            await wrapped_tool.ainvoke({})
                    
                    # 验证 Span 被创建（即使工具执行失败）
                    assert mock_langfuse_client.start_as_current_span.called
                    # 验证上下文管理器被正确退出（__exit__ 被调用）
                    assert mock_span_context.__exit__.called
    
    @pytest.mark.asyncio
    async def test_tool_span_creation_failure_isolation(self):
        """测试 Span 创建失败时不影响工具执行（错误隔离）"""
        # Arrange
        original_tool = test_async_tool
        wrapped_tool = TokenInjectedTool(tool=original_tool)
        token_id = "test_token_123"
        
        # Mock Langfuse 客户端，使其在创建 Span 时抛出异常
        mock_langfuse_client = MagicMock()
        mock_langfuse_client.start_as_current_span = MagicMock(side_effect=Exception("Span 创建失败"))
        
        with patch('domain.tools.wrapper.get_langfuse_client', return_value=mock_langfuse_client):
            with patch('domain.tools.wrapper.logger') as mock_logger:
                with patch.object(settings, 'LANGFUSE_ENABLED', True):
                    with patch.object(settings, 'LANGFUSE_ENABLE_SPANS', True):
                        # Act
                        with TokenContext(token_id=token_id):
                            result = await wrapped_tool.ainvoke({"param1": "value1"})
                        
                        # Assert
                        # 验证工具执行成功（即使 Span 创建失败）
                        assert "token_id=test_token_123" in result
                        assert "param1=value1" in result
                        
                        # 验证警告日志被记录
                        warning_calls = [call for call in mock_logger.warning.call_args_list 
                                       if '创建 Langfuse Span 失败' in str(call)]
                        assert len(warning_calls) > 0
    
    @pytest.mark.asyncio
    async def test_tool_span_when_langfuse_client_is_none(self):
        """测试 Langfuse 客户端为 None 时不创建 Span"""
        # Arrange
        original_tool = test_async_tool
        wrapped_tool = TokenInjectedTool(tool=original_tool)
        token_id = "test_token_123"
        
        with patch('domain.tools.wrapper.get_langfuse_client', return_value=None):
            with patch.object(settings, 'LANGFUSE_ENABLED', True):
                with patch.object(settings, 'LANGFUSE_ENABLE_SPANS', True):
                    # Act
                    with TokenContext(token_id=token_id):
                        result = await wrapped_tool.ainvoke({"param1": "value1"})
                    
                    # Assert
                    # 验证工具执行成功
                    assert "token_id=test_token_123" in result
                    assert "param1=value1" in result

