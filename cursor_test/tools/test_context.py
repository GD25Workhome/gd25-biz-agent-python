"""
工具上下文管理器测试

Pytest 命令示例：
================

# 运行整个测试文件
pytest cursor_test/tools/test_context.py

# 运行整个测试文件（详细输出）
pytest cursor_test/tools/test_context.py -v

# 运行整个测试文件（显示 print 输出）
pytest cursor_test/tools/test_context.py -s

# 运行特定的测试类
pytest cursor_test/tools/test_context.py::TestTokenContext

# 运行特定的测试方法
pytest cursor_test/tools/test_context.py::TestTokenContext::test_set_and_get_token_id
"""
import pytest
import contextvars
from domain.tools.context import TokenContext, get_token_id, set_token_id, _token_id_context


class TestTokenContext:
    """TokenContext 测试类"""
    
    def setup_method(self):
        """每个测试方法执行前清理上下文"""
        # 重置上下文变量
        try:
            _token_id_context.set(None)
        except Exception:
            pass
    """TokenContext 测试类"""
    
    def test_set_and_get_token_id(self):
        """测试设置和获取 tokenId"""
        # Arrange
        token_id = "test_token_123"
        
        # Act
        set_token_id(token_id)
        result = get_token_id()
        
        # Assert
        assert result == token_id
    
    def test_get_token_id_when_not_set(self):
        """测试未设置时获取 tokenId 返回 None"""
        # Arrange - 确保上下文为空
        # 由于 contextvars 的默认值是 None，直接获取应该返回 None
        # 但如果之前有设置，需要先清理
        try:
            _token_id_context.set(None)
        except Exception:
            pass
        
        # Act
        result = get_token_id()
        
        # Assert
        assert result is None
    
    def test_token_context_manager(self):
        """测试 TokenContext 上下文管理器"""
        # Arrange
        token_id = "test_token_456"
        
        # Act & Assert
        # 在上下文外部，tokenId 应该为 None
        assert get_token_id() is None
        
        # 进入上下文
        with TokenContext(token_id=token_id):
            # 在上下文内部，应该能获取到 tokenId
            assert get_token_id() == token_id
        
        # 退出上下文后，应该恢复为 None
        assert get_token_id() is None
    
    def test_token_context_nested(self):
        """测试嵌套的 TokenContext"""
        # Arrange
        outer_token = "outer_token"
        inner_token = "inner_token"
        
        # Act & Assert
        with TokenContext(token_id=outer_token):
            assert get_token_id() == outer_token
            
            # 嵌套内部上下文
            with TokenContext(token_id=inner_token):
                assert get_token_id() == inner_token
            
            # 退出内部上下文后，应该恢复为外部 tokenId
            assert get_token_id() == outer_token
        
        # 退出外部上下文后，应该为 None
        assert get_token_id() is None
    
    def test_token_context_multiple_entries(self):
        """测试多次进入同一个 TokenContext"""
        # Arrange
        token_id = "test_token_789"
        context = TokenContext(token_id=token_id)
        
        # Act & Assert
        with context:
            assert get_token_id() == token_id
        
        # 再次进入同一个上下文
        with context:
            assert get_token_id() == token_id
        
        # 退出后应该为 None
        assert get_token_id() is None
    
    def test_token_context_with_exception(self):
        """测试 TokenContext 在异常情况下也能正确恢复"""
        # Arrange
        token_id = "test_token_exception"
        
        # Act & Assert
        try:
            with TokenContext(token_id=token_id):
                assert get_token_id() == token_id
                # 模拟异常
                raise ValueError("测试异常")
        except ValueError:
            pass
        
        # 即使发生异常，上下文也应该正确恢复
        assert get_token_id() is None

