"""
Agent注册表测试
测试 AgentRegistry 类的注册、查询和动态加载功能

运行方式：
==========
# 直接运行测试文件
python cursor_test/M1_test/domain/test_agent_registry.py

# 或者在项目根目录运行
python -m cursor_test.M1_test.domain.test_agent_registry
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

from domain.agents.registry import AgentRegistry
from domain.agents.factory import AgentFactory
from infrastructure.prompts.placeholder import PlaceholderManager


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
                    "temperature": 0.7
                },
                "tools": [
                    "record_blood_pressure",
                    "query_blood_pressure"
                ],
                "langfuse_template": "blood_pressure_agent_prompt",
                "placeholders": {
                    "normal_range": "收缩压 90-140 mmHg，舒张压 60-90 mmHg"
                },
                "routing": {
                    "node_name": "blood_pressure_agent",
                    "intent_type": "blood_pressure"
                }
            },
            "appointment_agent": {
                "name": "复诊管理智能体",
                "description": "负责处理用户预约相关的请求",
                "llm": {
                    "temperature": 0.0
                },
                "tools": [
                    "create_appointment",
                    "query_appointment"
                ],
                "langfuse_template": "appointment_agent_prompt",
                "routing": {
                    "node_name": "appointment_agent",
                    "intent_type": "appointment"
                }
            }
        }
    }


def test_agent_registration():
    """测试Agent注册"""
    try:
        # 清除之前的注册
        AgentRegistry.clear()
        
        # 注册测试Agent
        test_config = {
            "name": "测试智能体",
            "llm": {"temperature": 0.5}
        }
        AgentRegistry.register("test_agent", test_config)
        
        # 验证注册
        assert AgentRegistry.is_registered("test_agent"), "Agent应该已注册"
        config = AgentRegistry.get_agent_config("test_agent")
        assert config is not None, "应该能获取Agent配置"
        assert config["name"] == "测试智能体", "配置应该正确"
        
        test_result.add_pass("test_agent_registration")
    except Exception as e:
        test_result.add_fail("test_agent_registration", str(e))


def test_load_from_config():
    """测试从配置文件加载"""
    try:
        # 清除之前的注册
        AgentRegistry.clear()
        PlaceholderManager.clear_agent_placeholders()
        
        # 保存原始配置
        original_config = AgentFactory._config.copy() if AgentFactory._config else {}
        original_config_path = AgentFactory._config_path
        
        try:
            # 创建临时配置文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                config = create_test_config()
                yaml.dump(config, f, allow_unicode=True)
                config_path = f.name
            
            try:
                # 加载配置
                AgentRegistry.load_from_config(config_path)
                
                # 验证加载
                agents = AgentRegistry.get_all_agents()
                assert len(agents) == 2, f"应该加载2个Agent，实际加载了{len(agents)}个"
                assert "blood_pressure_agent" in agents, "应该包含blood_pressure_agent"
                assert "appointment_agent" in agents, "应该包含appointment_agent"
                
                # 验证占位符加载
                bp_config = AgentRegistry.get_agent_config("blood_pressure_agent")
                assert "placeholders" in bp_config, "应该包含占位符配置"
                
                # 验证占位符已加载到PlaceholderManager
                placeholders = PlaceholderManager.get_placeholders("blood_pressure_agent", state=None)
                assert "normal_range" in placeholders, "应该包含normal_range占位符"
                
                test_result.add_pass("test_load_from_config")
            finally:
                # 清理临时文件
                if os.path.exists(config_path):
                    os.unlink(config_path)
        finally:
            # 恢复原始配置
            AgentFactory._config = original_config
            AgentFactory._config_path = original_config_path
            # 重新加载原始配置（如果存在）
            if original_config_path and os.path.exists(original_config_path):
                try:
                    AgentFactory.load_config(original_config_path)
                except:
                    pass
    except Exception as e:
        test_result.add_fail("test_load_from_config", str(e))


def test_get_agent_node_name():
    """测试获取Agent节点名称"""
    try:
        # 清除之前的注册
        AgentRegistry.clear()
        
        # 注册测试Agent（带routing配置）
        test_config = {
            "name": "测试智能体",
            "routing": {
                "node_name": "custom_node_name",
                "intent_type": "test_intent"
            }
        }
        AgentRegistry.register("test_agent", test_config)
        
        # 测试获取节点名称
        node_name = AgentRegistry.get_agent_node_name("test_agent")
        assert node_name == "custom_node_name", f"应该返回custom_node_name，实际返回{node_name}"
        
        # 测试没有routing配置的情况
        test_config2 = {
            "name": "测试智能体2"
        }
        AgentRegistry.register("test_agent2", test_config2)
        node_name2 = AgentRegistry.get_agent_node_name("test_agent2")
        assert node_name2 == "test_agent2", f"应该返回agent_key，实际返回{node_name2}"
        
        test_result.add_pass("test_get_agent_node_name")
    except Exception as e:
        test_result.add_fail("test_get_agent_node_name", str(e))


def test_get_agent_intent_type():
    """测试获取Agent意图类型"""
    try:
        # 清除之前的注册
        AgentRegistry.clear()
        
        # 注册测试Agent（带routing配置）
        test_config = {
            "name": "测试智能体",
            "routing": {
                "node_name": "test_agent",
                "intent_type": "test_intent"
            }
        }
        AgentRegistry.register("test_agent", test_config)
        
        # 测试获取意图类型
        intent_type = AgentRegistry.get_agent_intent_type("test_agent")
        assert intent_type == "test_intent", f"应该返回test_intent，实际返回{intent_type}"
        
        # 测试没有routing配置的情况
        test_config2 = {
            "name": "测试智能体2"
        }
        AgentRegistry.register("test_agent2", test_config2)
        intent_type2 = AgentRegistry.get_agent_intent_type("test_agent2")
        assert intent_type2 is None, f"应该返回None，实际返回{intent_type2}"
        
        test_result.add_pass("test_get_agent_intent_type")
    except Exception as e:
        test_result.add_fail("test_get_agent_intent_type", str(e))


def test_is_registered():
    """测试检查Agent是否已注册"""
    try:
        # 清除之前的注册
        AgentRegistry.clear()
        
        # 测试未注册的Agent
        assert not AgentRegistry.is_registered("non_existent_agent"), "未注册的Agent应该返回False"
        
        # 注册Agent
        AgentRegistry.register("test_agent", {"name": "测试智能体"})
        
        # 测试已注册的Agent
        assert AgentRegistry.is_registered("test_agent"), "已注册的Agent应该返回True"
        
        test_result.add_pass("test_is_registered")
    except Exception as e:
        test_result.add_fail("test_is_registered", str(e))


def test_clear():
    """测试清除注册"""
    try:
        # 清除之前的注册（可能包含从配置文件加载的Agent）
        AgentRegistry.clear()
        
        # 注册一些Agent
        AgentRegistry.register("test_agent1", {"name": "测试智能体1"})
        AgentRegistry.register("test_agent2", {"name": "测试智能体2"})
        
        # 验证已注册（直接访问_agents，避免触发自动加载）
        assert len(AgentRegistry._agents) >= 2, f"应该至少有2个Agent，实际有{len(AgentRegistry._agents)}个"
        assert "test_agent1" in AgentRegistry._agents, "应该包含test_agent1"
        assert "test_agent2" in AgentRegistry._agents, "应该包含test_agent2"
        
        # 清除注册
        AgentRegistry.clear()
        
        # 验证已清除（直接访问_agents，避免触发自动加载）
        assert len(AgentRegistry._agents) == 0, "应该没有Agent"
        assert not AgentRegistry._initialized, "应该标记为未初始化"
        
        test_result.add_pass("test_clear")
    except Exception as e:
        test_result.add_fail("test_clear", str(e))


def test_integration_with_factory():
    """测试与AgentFactory的集成"""
    try:
        # 清除之前的注册
        AgentRegistry.clear()
        AgentFactory._config = {}
        
        # 创建临时配置文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config = create_test_config()
            yaml.dump(config, f, allow_unicode=True)
            config_path = f.name
        
        try:
            # 通过AgentRegistry加载配置（会调用AgentFactory.load_config）
            AgentRegistry.load_from_config(config_path)
            
            # 验证AgentFactory也加载了配置
            assert len(AgentFactory._config) == 2, "AgentFactory应该也加载了配置"
            
            # 验证可以通过AgentFactory创建Agent
            # 注意：这里不实际创建Agent，因为需要LLM和工具，只验证配置已加载
            agents = AgentFactory.list_agents()
            assert "blood_pressure_agent" in agents, "应该能列出blood_pressure_agent"
            assert "appointment_agent" in agents, "应该能列出appointment_agent"
            
            test_result.add_pass("test_integration_with_factory")
        finally:
            # 清理临时文件
            if os.path.exists(config_path):
                os.unlink(config_path)
    except Exception as e:
        test_result.add_fail("test_integration_with_factory", str(e))


def main():
    """运行所有测试"""
    print("="*60)
    print("AgentRegistry 测试")
    print("="*60)
    print()
    
    # 运行测试
    test_agent_registration()
    test_load_from_config()
    test_get_agent_node_name()
    test_get_agent_intent_type()
    test_is_registered()
    test_clear()
    test_integration_with_factory()
    
    # 打印总结
    success = test_result.summary()
    
    # 清理
    AgentRegistry.clear()
    PlaceholderManager.clear_agent_placeholders()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

