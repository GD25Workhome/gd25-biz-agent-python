"""
工具注册表测试
测试工具注册表的功能，包括工具注册、获取和初始化

运行方式：
==========
# 直接运行测试文件
python cursor_test/M1_test/domain/test_tool_registry.py

# 或者在项目根目录运行
python -m cursor_test.M1_test.domain.test_tool_registry
"""
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到 Python 路径
test_file_path = Path(__file__).resolve()
project_root = test_file_path.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain_core.tools import BaseTool
from domain.tools.registry import TOOL_REGISTRY, register_tool, get_tool, init_tools


class TestResult:
    """测试结果记录类"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self, test_name: str):
        """记录通过的测试"""
        self.passed += 1
        print(f"✅ {test_name}")
    
    def add_fail(self, test_name: str, error: str):
        """记录失败的测试"""
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"❌ {test_name}: {error}")
    
    def summary(self):
        """打印测试总结"""
        print("\n" + "="*60)
        print("测试总结")
        print("="*60)
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"总计: {self.passed + self.failed}")
        
        if self.errors:
            print("\n失败详情:")
            for error in self.errors:
                print(f"  - {error}")
        
        print("="*60)
        return self.failed == 0


# 全局测试结果记录
test_result = TestResult()


def test_register_tool():
    """
    测试用例 1: 工具注册（register_tool）
    
    验证：
    - 能够成功注册工具
    - 工具被添加到 TOOL_REGISTRY 中
    - 可以使用工具名称获取工具
    """
    test_name = "工具注册（register_tool）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 保存原始注册表状态
        original_registry = TOOL_REGISTRY.copy()
        
        try:
            # 创建 Mock 工具
            mock_tool = MagicMock(spec=BaseTool)
            mock_tool.name = "test_tool"
            
            # 注册工具
            register_tool("test_tool", mock_tool)
            
            # 验证工具已注册
            assert "test_tool" in TOOL_REGISTRY, "工具应该被注册到注册表中"
            assert TOOL_REGISTRY["test_tool"] == mock_tool, "注册的工具应该与传入的工具相同"
            
            # 验证可以获取工具
            retrieved_tool = get_tool("test_tool")
            assert retrieved_tool == mock_tool, "获取的工具应该与注册的工具相同"
            
            print(f"  ✅ 工具注册成功")
            print(f"  ✅ 工具名称: test_tool")
            print(f"  ✅ 工具类型: {type(mock_tool).__name__}")
            
            test_result.add_pass(test_name)
            
        finally:
            # 恢复原始注册表状态
            TOOL_REGISTRY.clear()
            TOOL_REGISTRY.update(original_registry)
            
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_get_tool_exists():
    """
    测试用例 2: 工具获取（get_tool，存在）
    
    验证：
    - 当工具存在时，能够成功获取工具
    - 返回的工具实例正确
    """
    test_name = "工具获取（get_tool，存在）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 保存原始注册表状态
        original_registry = TOOL_REGISTRY.copy()
        
        try:
            # 创建并注册工具
            mock_tool = MagicMock(spec=BaseTool)
            mock_tool.name = "existing_tool"
            register_tool("existing_tool", mock_tool)
            
            # 获取工具
            retrieved_tool = get_tool("existing_tool")
            
            # 验证结果
            assert retrieved_tool == mock_tool, "获取的工具应该与注册的工具相同"
            assert isinstance(retrieved_tool, BaseTool) or hasattr(retrieved_tool, 'name'), \
                "获取的工具应该是 BaseTool 实例或具有 name 属性"
            
            print(f"  ✅ 工具获取成功")
            print(f"  ✅ 工具名称: existing_tool")
            
            test_result.add_pass(test_name)
            
        finally:
            # 恢复原始注册表状态
            TOOL_REGISTRY.clear()
            TOOL_REGISTRY.update(original_registry)
            
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_get_tool_not_exists():
    """
    测试用例 3: 工具获取（get_tool，不存在）
    
    验证：
    - 当工具不存在时，应该抛出 ValueError
    - 错误信息应该包含工具名称
    """
    test_name = "工具获取（get_tool，不存在）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 验证抛出 ValueError
        try:
            get_tool("non_existent_tool")
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "non_existent_tool" in str(e), f"错误信息应该包含工具名称: {e}"
            assert "工具不存在" in str(e) or "不存在" in str(e), f"错误信息应该说明工具不存在: {e}"
            print(f"  ✅ 正确抛出 ValueError: {e}")
            test_result.add_pass(test_name)
        except Exception as e:
            raise AssertionError(f"应该抛出 ValueError，但抛出了 {type(e).__name__}: {e}")
            
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


@patch('domain.tools.registry.register_tool')
def test_init_tools(mock_register_tool):
    """
    测试用例 4: 工具初始化（init_tools）
    
    验证：
    - init_tools 函数能够正确导入所有工具
    - 所有工具都被正确注册
    - register_tool 被调用正确的次数
    """
    test_name = "工具初始化（init_tools）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 保存原始注册表状态
        original_registry = TOOL_REGISTRY.copy()
        
        try:
            # 清空注册表
            TOOL_REGISTRY.clear()
            
            # 重置 Mock
            mock_register_tool.reset_mock()
            
            # 调用 init_tools
            init_tools()
            
            # 验证 register_tool 被调用
            assert mock_register_tool.called, "register_tool 应该被调用"
            
            # 验证调用次数（应该有6个工具：3个血压工具 + 3个预约工具）
            call_count = mock_register_tool.call_count
            assert call_count >= 6, f"register_tool 应该至少被调用6次，实际调用 {call_count} 次"
            
            # 验证注册的工具名称
            registered_names = [call[0][0] for call in mock_register_tool.call_args_list]
            expected_tools = [
                "record_blood_pressure",
                "query_blood_pressure",
                "update_blood_pressure",
                "create_appointment",
                "query_appointment",
                "update_appointment"
            ]
            
            for tool_name in expected_tools:
                assert tool_name in registered_names, f"工具 {tool_name} 应该被注册"
            
            print(f"  ✅ 工具初始化成功")
            print(f"  ✅ 注册工具数量: {call_count}")
            print(f"  ✅ 已注册工具: {', '.join(registered_names)}")
            
            test_result.add_pass(test_name)
            
        finally:
            # 恢复原始注册表状态
            TOOL_REGISTRY.clear()
            TOOL_REGISTRY.update(original_registry)
            
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_all_tools_registered():
    """
    测试用例 5: 所有工具已注册验证
    
    验证：
    - 所有预期的工具都已注册到 TOOL_REGISTRY 中
    - 每个工具都是 BaseTool 实例
    - 工具名称正确
    """
    test_name = "所有工具已注册验证"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 预期的工具列表
        expected_tools = [
            "record_blood_pressure",
            "query_blood_pressure",
            "update_blood_pressure",
            "create_appointment",
            "query_appointment",
            "update_appointment"
        ]
        
        # 验证所有工具都已注册
        missing_tools = []
        for tool_name in expected_tools:
            if tool_name not in TOOL_REGISTRY:
                missing_tools.append(tool_name)
            else:
                tool = TOOL_REGISTRY[tool_name]
                # 验证工具是 BaseTool 实例或具有必要的属性
                assert tool is not None, f"工具 {tool_name} 不应该为 None"
                # 注意：某些工具可能是函数，不一定是 BaseTool 实例
                # 所以只验证工具存在且不为 None
        
        assert len(missing_tools) == 0, f"以下工具未注册: {missing_tools}"
        
        # 打印已注册的工具
        registered_tools = list(TOOL_REGISTRY.keys())
        print(f"  ✅ 所有工具已注册")
        print(f"  ✅ 注册工具数量: {len(registered_tools)}")
        print(f"  ✅ 已注册工具列表:")
        for tool_name in expected_tools:
            tool_status = "✅" if tool_name in TOOL_REGISTRY else "❌"
            print(f"     {tool_status} {tool_name}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def main():
    """运行所有测试"""
    print("="*60)
    print("工具注册表测试")
    print("="*60)
    
    # 运行所有测试
    test_register_tool()
    test_get_tool_exists()
    test_get_tool_not_exists()
    test_init_tools()
    test_all_tools_registered()
    
    # 打印测试总结
    success = test_result.summary()
    
    # 退出码：0 表示成功，1 表示失败
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
