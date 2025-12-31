"""
TokenId 自动注入集成测试
测试工具包装器和 TokenContext 的完整集成流程

Pytest 命令示例：
================

# 运行整个测试文件
pytest cursor_test/tools/test_token_injection_integration.py

# 运行整个测试文件（详细输出）
pytest cursor_test/tools/test_token_injection_integration.py -v

# 运行整个测试文件（显示 print 输出）
pytest cursor_test/tools/test_token_injection_integration.py -s

# 运行特定的测试类
pytest cursor_test/tools/test_token_injection_integration.py::TestTokenInjectionIntegration

# 运行特定的测试方法
pytest cursor_test/tools/test_token_injection_integration.py::TestTokenInjectionIntegration::test_tool_wrapper_with_token_context
"""
import pytest
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain_core.tools import tool
from domain.tools.context import TokenContext
from domain.tools.wrapper import TokenInjectedTool, wrap_tools_with_token_context
from domain.tools.utils.token_converter import convert_token_to_user_info


# 创建一个测试工具，模拟实际工具的行为
@tool
async def test_record_tool(token_id: str, value: int) -> str:
    """测试记录工具"""
    # 验证 token_id 已被注入
    user_info = convert_token_to_user_info(token_id)
    return f"记录成功: value={value}, user_id={user_info.user_id}"


class TestTokenInjectionIntegration:
    """TokenId 自动注入集成测试类"""
    
    def setup_method(self):
        """每个测试方法执行前清理上下文"""
        from domain.tools.context import _token_id_context
        try:
            _token_id_context.set(None)
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_tool_wrapper_with_token_context(self):
        """测试工具包装器与 TokenContext 的集成"""
        # Arrange
        original_tool = test_record_tool
        wrapped_tool = TokenInjectedTool(tool=original_tool)
        token_id = "test_token_123"
        
        # Act
        with TokenContext(token_id=token_id):
            result = await wrapped_tool.ainvoke({"value": 100})
        
        # Assert
        assert "记录成功" in result
        assert "user_id=test_token_123" in result
        assert "value=100" in result
    
    @pytest.mark.asyncio
    async def test_wrap_tools_integration(self):
        """测试批量包装工具的集成"""
        # Arrange
        tools = [test_record_tool]
        wrapped_tools = wrap_tools_with_token_context(tools)
        token_id = "test_token_456"
        
        # Act
        with TokenContext(token_id=token_id):
            result = await wrapped_tools[0].ainvoke({"value": 200})
        
        # Assert
        assert "记录成功" in result
        assert "user_id=test_token_456" in result
        assert "value=200" in result
    
    @pytest.mark.asyncio
    async def test_token_converter_integration(self):
        """测试数据转换器的集成"""
        # Arrange
        token_id = "test_token_789"
        
        # Act
        user_info = convert_token_to_user_info(token_id)
        user_id = user_info.user_id
        
        # Assert
        assert user_id == token_id
        assert user_info.user_id == "test_token_789"
    
    @pytest.mark.asyncio
    async def test_multiple_tools_with_same_context(self):
        """测试多个工具在同一个上下文中使用"""
        # Arrange
        tools = [test_record_tool, test_record_tool]
        wrapped_tools = wrap_tools_with_token_context(tools)
        token_id = "test_token_multi"
        
        # Act
        with TokenContext(token_id=token_id):
            result1 = await wrapped_tools[0].ainvoke({"value": 300})
            result2 = await wrapped_tools[1].ainvoke({"value": 400})
        
        # Assert
        assert "user_id=test_token_multi" in result1
        assert "user_id=test_token_multi" in result2
        assert "value=300" in result1
        assert "value=400" in result2
    
    @pytest.mark.asyncio
    async def test_nested_token_context(self):
        """测试嵌套的 TokenContext"""
        # Arrange
        wrapped_tool = TokenInjectedTool(tool=test_record_tool)
        outer_token = "outer_token"
        inner_token = "inner_token"
        
        # Act
        with TokenContext(token_id=outer_token):
            result1 = await wrapped_tool.ainvoke({"value": 500})
            
            with TokenContext(token_id=inner_token):
                result2 = await wrapped_tool.ainvoke({"value": 600})
            
            result3 = await wrapped_tool.ainvoke({"value": 700})
        
        # Assert
        assert "user_id=outer_token" in result1
        assert "user_id=inner_token" in result2
        assert "user_id=outer_token" in result3

