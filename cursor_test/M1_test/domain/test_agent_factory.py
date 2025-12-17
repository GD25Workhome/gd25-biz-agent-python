"""
智能体工厂测试
测试 AgentFactory 类的配置加载和智能体创建功能

运行方式：
==========
# 直接运行测试文件
python cursor_test/M1_test/domain/test_agent_factory.py

# 或者在项目根目录运行
python -m cursor_test.M1_test.domain.test_agent_factory
"""
import sys
import os
import tempfile
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到 Python 路径
test_file_path = Path(__file__).resolve()
project_root = test_file_path.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from domain.agents.factory import AgentFactory


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


def create_test_config():
    """创建测试配置文件内容"""
    return {
        "agents": {
            "blood_pressure_agent": {
                "name": "血压记录智能体",
                "description": "负责处理用户血压相关的请求",
                "llm": {
                    "model": "test-model",
                    "temperature": 0.0
                },
                "tools": [
                    "record_blood_pressure",
                    "query_blood_pressure"
                ],
                "system_prompt": "你是一个血压记录助手"
            },
            "appointment_agent": {
                "name": "复诊管理智能体",
                "description": "负责处理用户预约相关的请求",
                "llm": {
                    "model": "test-model",
                    "temperature": 0.0
                },
                "tools": [
                    "create_appointment",
                    "query_appointment"
                ],
                "system_prompt": "你是一个复诊管理助手"
            }
        }
    }


def test_load_config():
    """
    测试用例 1: load_config（加载配置文件）
    
    验证：
    - 能够成功加载配置文件
    - 配置内容正确解析
    - _config 属性被正确设置
    """
    test_name = "load_config（加载配置文件）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 创建临时配置文件
        config_data = create_test_config()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            yaml.dump(config_data, f, allow_unicode=True)
            temp_config_path = f.name
        
        try:
            # 重置工厂状态
            AgentFactory._config = {}
            
            # 加载配置
            AgentFactory.load_config(temp_config_path)
            
            # 验证配置已加载
            assert AgentFactory._config != {}, "配置应该被加载"
            assert "blood_pressure_agent" in AgentFactory._config, "应该包含血压智能体配置"
            assert "appointment_agent" in AgentFactory._config, "应该包含预约智能体配置"
            
            # 验证配置内容
            bp_config = AgentFactory._config["blood_pressure_agent"]
            assert bp_config["name"] == "血压记录智能体", "智能体名称应该正确"
            assert "tools" in bp_config, "应该包含工具列表"
            
            print(f"  ✅ 配置已成功加载")
            print(f"  ✅ 智能体数量: {len(AgentFactory._config)}")
            
            test_result.add_pass(test_name)
            
        finally:
            # 清理临时文件
            if os.path.exists(temp_config_path):
                os.unlink(temp_config_path)
            
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_load_config_not_found():
    """
    测试用例 2: load_config（配置文件不存在）
    
    验证：
    - 当配置文件不存在时，应该抛出 FileNotFoundError
    """
    test_name = "load_config（配置文件不存在）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 重置工厂状态
        AgentFactory._config = {}
        
        # 使用不存在的配置文件路径
        non_existent_path = "/tmp/non_existent_config_12345.yaml"
        
        # 验证抛出 FileNotFoundError
        try:
            AgentFactory.load_config(non_existent_path)
            assert False, "应该抛出 FileNotFoundError"
        except FileNotFoundError as e:
            assert non_existent_path in str(e), f"错误信息应该包含文件路径: {e}"
            print(f"  ✅ 正确抛出 FileNotFoundError: {e}")
            test_result.add_pass(test_name)
        except Exception as e:
            raise AssertionError(f"应该抛出 FileNotFoundError，但抛出了 {type(e).__name__}: {e}")
            
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


@patch('domain.agents.factory.get_llm')
@patch('domain.agents.factory.create_react_agent')
@patch('domain.agents.factory.TOOL_REGISTRY')
def test_create_agent_blood_pressure(mock_tool_registry, mock_create_agent, mock_get_llm):
    """
    测试用例 3: create_agent（创建血压智能体）
    
    验证：
    - 能够成功创建血压智能体
    - 使用正确的配置参数
    - 调用 create_react_agent 时传入正确的参数
    """
    test_name = "create_agent（创建血压智能体）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 准备 Mock 对象
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_tool1 = MagicMock(spec=BaseTool)
        mock_tool2 = MagicMock(spec=BaseTool)
        mock_agent = MagicMock()
        
        mock_get_llm.return_value = mock_llm
        mock_tool_registry.__getitem__.side_effect = lambda key: {
            "record_blood_pressure": mock_tool1,
            "query_blood_pressure": mock_tool2
        }.get(key, None)
        mock_tool_registry.__contains__.side_effect = lambda key: key in ["record_blood_pressure", "query_blood_pressure"]
        mock_create_agent.return_value = mock_agent
        
        # 创建测试配置
        config_data = create_test_config()
        AgentFactory._config = config_data["agents"]
        
        # 创建智能体
        agent = AgentFactory.create_agent("blood_pressure_agent")
        
        # 验证结果
        assert agent == mock_agent, "应该返回创建的智能体实例"
        
        # 验证 get_llm 被调用
        mock_get_llm.assert_called_once()
        call_args = mock_get_llm.call_args
        assert call_args[1]["model"] == "test-model", "应该使用配置中的模型"
        assert call_args[1]["temperature"] == 0.0, "应该使用配置中的温度"
        
        # 验证 create_react_agent 被调用
        mock_create_agent.assert_called_once()
        create_args = mock_create_agent.call_args
        assert create_args[1]["model"] == mock_llm, "应该传入 LLM 实例"
        assert len(create_args[1]["tools"]) == 2, "应该传入2个工具"
        assert create_args[1]["prompt"] == "你是一个血压记录助手", "应该使用配置中的提示词"
        
        print(f"  ✅ 血压智能体创建成功")
        print(f"  ✅ LLM 配置正确")
        print(f"  ✅ 工具数量: {len(create_args[1]['tools'])}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


@patch('domain.agents.factory.get_llm')
@patch('domain.agents.factory.create_react_agent')
@patch('domain.agents.factory.TOOL_REGISTRY')
def test_create_agent_appointment(mock_tool_registry, mock_create_agent, mock_get_llm):
    """
    测试用例 4: create_agent（创建预约智能体）
    
    验证：
    - 能够成功创建预约智能体
    - 使用正确的配置参数
    """
    test_name = "create_agent（创建预约智能体）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 准备 Mock 对象
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_tool1 = MagicMock(spec=BaseTool)
        mock_tool2 = MagicMock(spec=BaseTool)
        mock_agent = MagicMock()
        
        mock_get_llm.return_value = mock_llm
        mock_tool_registry.__getitem__.side_effect = lambda key: {
            "create_appointment": mock_tool1,
            "query_appointment": mock_tool2
        }.get(key, None)
        mock_tool_registry.__contains__.side_effect = lambda key: key in ["create_appointment", "query_appointment"]
        mock_create_agent.return_value = mock_agent
        
        # 创建测试配置
        config_data = create_test_config()
        AgentFactory._config = config_data["agents"]
        
        # 创建智能体
        agent = AgentFactory.create_agent("appointment_agent")
        
        # 验证结果
        assert agent == mock_agent, "应该返回创建的智能体实例"
        
        # 验证 create_react_agent 被调用
        mock_create_agent.assert_called_once()
        create_args = mock_create_agent.call_args
        assert create_args[1]["prompt"] == "你是一个复诊管理助手", "应该使用配置中的提示词"
        
        print(f"  ✅ 预约智能体创建成功")
        print(f"  ✅ 提示词正确")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_create_agent_not_found():
    """
    测试用例 5: create_agent（智能体配置不存在）
    
    验证：
    - 当智能体配置不存在时，应该抛出 ValueError
    """
    test_name = "create_agent（智能体配置不存在）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 创建测试配置（包含一个智能体，但不包含要查找的智能体）
        config_data = create_test_config()
        AgentFactory._config = config_data["agents"]
        
        # 验证抛出 ValueError
        try:
            AgentFactory.create_agent("non_existent_agent")
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "non_existent_agent" in str(e), f"错误信息应该包含智能体键名: {e}"
            print(f"  ✅ 正确抛出 ValueError: {e}")
            test_result.add_pass(test_name)
        except Exception as e:
            raise AssertionError(f"应该抛出 ValueError，但抛出了 {type(e).__name__}: {e}")
            
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


@patch('domain.agents.factory.create_react_agent')
@patch('domain.agents.factory.TOOL_REGISTRY')
def test_create_agent_custom_llm(mock_tool_registry, mock_create_agent):
    """
    测试用例 6: create_agent（自定义 LLM）
    
    验证：
    - 当提供自定义 LLM 时，应该使用自定义 LLM 而不是配置中的 LLM
    - get_llm 不应该被调用
    """
    test_name = "create_agent（自定义 LLM）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 准备 Mock 对象
        custom_llm = MagicMock(spec=BaseChatModel)
        mock_tool = MagicMock(spec=BaseTool)
        mock_agent = MagicMock()
        
        mock_tool_registry.__getitem__.side_effect = lambda key: mock_tool
        mock_tool_registry.__contains__.side_effect = lambda key: True
        mock_create_agent.return_value = mock_agent
        
        # 创建测试配置
        config_data = create_test_config()
        AgentFactory._config = config_data["agents"]
        
        # 使用自定义 LLM 创建智能体
        with patch('domain.agents.factory.get_llm') as mock_get_llm:
            agent = AgentFactory.create_agent("blood_pressure_agent", llm=custom_llm)
            
            # 验证 get_llm 没有被调用
            mock_get_llm.assert_not_called()
            
            # 验证 create_react_agent 使用了自定义 LLM
            mock_create_agent.assert_called_once()
            create_args = mock_create_agent.call_args
            assert create_args[1]["model"] == custom_llm, "应该使用自定义 LLM"
            
            print(f"  ✅ 使用了自定义 LLM")
            print(f"  ✅ get_llm 未被调用")
            
            test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


@patch('domain.agents.factory.get_llm')
@patch('domain.agents.factory.create_react_agent')
def test_create_agent_custom_tools(mock_create_agent, mock_get_llm):
    """
    测试用例 7: create_agent（自定义工具）
    
    验证：
    - 当提供自定义工具列表时，应该使用自定义工具而不是配置中的工具
    - TOOL_REGISTRY 不应该被访问
    """
    test_name = "create_agent（自定义工具）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 准备 Mock 对象
        mock_llm = MagicMock(spec=BaseChatModel)
        custom_tool1 = MagicMock(spec=BaseTool)
        custom_tool2 = MagicMock(spec=BaseTool)
        custom_tools = [custom_tool1, custom_tool2]
        mock_agent = MagicMock()
        
        mock_get_llm.return_value = mock_llm
        mock_create_agent.return_value = mock_agent
        
        # 创建测试配置
        config_data = create_test_config()
        AgentFactory._config = config_data["agents"]
        
        # 使用自定义工具创建智能体
        with patch('domain.agents.factory.TOOL_REGISTRY') as mock_tool_registry:
            agent = AgentFactory.create_agent("blood_pressure_agent", tools=custom_tools)
            
            # 验证 TOOL_REGISTRY 没有被访问
            assert not hasattr(mock_tool_registry, '__getitem__') or not mock_tool_registry.__getitem__.called, \
                "TOOL_REGISTRY 不应该被访问"
            
            # 验证 create_react_agent 使用了自定义工具
            mock_create_agent.assert_called_once()
            create_args = mock_create_agent.call_args
            assert create_args[1]["tools"] == custom_tools, "应该使用自定义工具列表"
            assert len(create_args[1]["tools"]) == 2, "应该包含2个自定义工具"
            
            print(f"  ✅ 使用了自定义工具")
            print(f"  ✅ 工具数量: {len(custom_tools)}")
            
            test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


@patch('domain.agents.factory.get_llm')
@patch('domain.agents.factory.create_react_agent')
@patch('domain.agents.factory.TOOL_REGISTRY')
def test_create_agent_prompt_from_file(mock_tool_registry, mock_create_agent, mock_get_llm):
    """
    测试用例 8: create_agent（从文件加载提示词）
    
    验证：
    - 当配置中有 system_prompt_path 且文件存在时，应该从文件加载提示词
    - 文件内容应该覆盖配置中的 system_prompt
    """
    test_name = "create_agent（从文件加载提示词）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 创建临时提示词文件
        prompt_content = "这是从文件加载的提示词内容"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(prompt_content)
            temp_prompt_path = f.name
        
        try:
            # 准备 Mock 对象
            mock_llm = MagicMock(spec=BaseChatModel)
            mock_tool = MagicMock(spec=BaseTool)
            mock_agent = MagicMock()
            
            mock_get_llm.return_value = mock_llm
            mock_tool_registry.__getitem__.side_effect = lambda key: mock_tool
            mock_tool_registry.__contains__.side_effect = lambda key: True
            mock_create_agent.return_value = mock_agent
            
            # 创建测试配置（包含 system_prompt_path）
            config_data = create_test_config()
            config_data["agents"]["blood_pressure_agent"]["system_prompt_path"] = temp_prompt_path
            AgentFactory._config = config_data["agents"]
            
            # 创建智能体
            agent = AgentFactory.create_agent("blood_pressure_agent")
            
            # 验证 create_react_agent 使用了文件中的提示词
            mock_create_agent.assert_called_once()
            create_args = mock_create_agent.call_args
            assert create_args[1]["prompt"] == prompt_content, "应该使用文件中的提示词"
            
            print(f"  ✅ 从文件加载提示词成功")
            print(f"  ✅ 提示词内容: {prompt_content[:50]}...")
            
            test_result.add_pass(test_name)
            
        finally:
            # 清理临时文件
            if os.path.exists(temp_prompt_path):
                os.unlink(temp_prompt_path)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_list_agents():
    """
    测试用例 9: list_agents（列出所有智能体）
    
    验证：
    - 能够列出所有已配置的智能体
    - 返回的列表包含所有智能体键名
    """
    test_name = "list_agents（列出所有智能体）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 创建测试配置
        config_data = create_test_config()
        AgentFactory._config = config_data["agents"]
        
        # 列出所有智能体
        agents = AgentFactory.list_agents()
        
        # 验证结果
        assert isinstance(agents, list), "应该返回列表"
        assert len(agents) == 2, "应该包含2个智能体"
        assert "blood_pressure_agent" in agents, "应该包含血压智能体"
        assert "appointment_agent" in agents, "应该包含预约智能体"
        
        print(f"  ✅ 智能体列表: {agents}")
        print(f"  ✅ 智能体数量: {len(agents)}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def main():
    """运行所有测试"""
    print("="*60)
    print("智能体工厂测试")
    print("="*60)
    
    # 运行所有测试
    test_load_config()
    test_load_config_not_found()
    test_create_agent_blood_pressure()
    test_create_agent_appointment()
    test_create_agent_not_found()
    test_create_agent_custom_llm()
    test_create_agent_custom_tools()
    test_create_agent_prompt_from_file()
    test_list_agents()
    
    # 打印测试总结
    success = test_result.summary()
    
    # 退出码：0 表示成功，1 表示失败
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
