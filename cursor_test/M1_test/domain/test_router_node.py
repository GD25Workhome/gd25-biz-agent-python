"""
路由节点测试
测试 route_node 函数的路由逻辑

运行方式：
==========
# 直接运行测试文件
python cursor_test/M1_test/domain/test_router_node.py

# 或者在项目根目录运行
python -m cursor_test.M1_test.domain.test_router_node
"""
import sys
import os
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到 Python 路径
# test_router_node.py 位于: cursor_test/M1_test/domain/test_router_node.py
# 项目根目录: cursor_test/M1_test/domain/../../../
test_file_path = Path(__file__).resolve()
project_root = test_file_path.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from domain.router.state import RouterState
from domain.router.node import route_node


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


def print_state_info(state: RouterState, prefix: str = ""):
    """打印状态信息，方便调试"""
    print(f"{prefix}状态信息:")
    print(f"{prefix}  - current_intent: {state.get('current_intent')}")
    print(f"{prefix}  - current_agent: {state.get('current_agent')}")
    print(f"{prefix}  - need_reroute: {state.get('need_reroute')}")
    print(f"{prefix}  - session_id: {state.get('session_id')}")
    print(f"{prefix}  - user_id: {state.get('user_id')}")
    print(f"{prefix}  - messages 数量: {len(state.get('messages', []))}")


def test_route_node_blood_pressure_intent():
    """
    测试用例 1: route_node（识别血压意图）
    
    验证：
    - 当用户消息包含血压相关关键词时，能够正确识别为血压意图
    - current_intent 应该设置为 "blood_pressure"
    - current_agent 应该设置为 "blood_pressure_agent"
    - need_reroute 应该设置为 False
    """
    test_name = "route_node（识别血压意图）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 创建初始状态
        initial_state: RouterState = {
            "messages": [
                HumanMessage(content="我想记录血压，收缩压120，舒张压80")
            ],
            "current_intent": None,
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_001",
            "user_id": "test_user_001"
        }
        
        print("\n初始状态:")
        print_state_info(initial_state, "  ")
        print(f"\n用户消息: {initial_state['messages'][0].content}")
        
        # 执行路由节点
        print("\n执行 route_node...")
        result_state = route_node(initial_state)
        
        print("\n路由后的状态:")
        print_state_info(result_state, "  ")
        
        # 验证结果
        print("\n验证结果:")
        assert result_state["current_intent"] == "blood_pressure", \
            f"current_intent 应该是 'blood_pressure'，实际为: {result_state['current_intent']}"
        print("  ✓ current_intent 正确设置为 'blood_pressure'")
        
        assert result_state["current_agent"] == "blood_pressure_agent", \
            f"current_agent 应该是 'blood_pressure_agent'，实际为: {result_state['current_agent']}"
        print("  ✓ current_agent 正确设置为 'blood_pressure_agent'")
        
        assert result_state["need_reroute"] == False, \
            f"need_reroute 应该是 False，实际为: {result_state['need_reroute']}"
        print("  ✓ need_reroute 正确设置为 False")
        
        # 验证消息列表没有被修改
        assert len(result_state["messages"]) == len(initial_state["messages"]), \
            "消息列表长度不应该改变"
        print("  ✓ 消息列表未被修改")
        
        # 验证其他字段保持不变
        assert result_state["session_id"] == initial_state["session_id"], \
            "session_id 不应该改变"
        assert result_state["user_id"] == initial_state["user_id"], \
            "user_id 不应该改变"
        print("  ✓ session_id 和 user_id 保持不变")
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, str(e))
        import traceback
        traceback.print_exc()
        raise


def test_route_node_appointment_intent():
    """
    测试用例 2: route_node（识别预约意图）
    
    验证：
    - 当用户消息包含预约相关关键词时，能够正确识别为预约意图
    - current_intent 应该设置为 "appointment"
    - current_agent 应该设置为 "appointment_agent"
    - need_reroute 应该设置为 False
    """
    test_name = "route_node（识别预约意图）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 创建初始状态
        initial_state: RouterState = {
            "messages": [
                HumanMessage(content="我想预约内科")
            ],
            "current_intent": None,
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_002",
            "user_id": "test_user_002"
        }
        
        print("\n初始状态:")
        print_state_info(initial_state, "  ")
        print(f"\n用户消息: {initial_state['messages'][0].content}")
        
        # 执行路由节点
        print("\n执行 route_node...")
        result_state = route_node(initial_state)
        
        print("\n路由后的状态:")
        print_state_info(result_state, "  ")
        
        # 验证结果
        print("\n验证结果:")
        assert result_state["current_intent"] == "appointment", \
            f"current_intent 应该是 'appointment'，实际为: {result_state['current_intent']}"
        print("  ✓ current_intent 正确设置为 'appointment'")
        
        assert result_state["current_agent"] == "appointment_agent", \
            f"current_agent 应该是 'appointment_agent'，实际为: {result_state['current_agent']}"
        print("  ✓ current_agent 正确设置为 'appointment_agent'")
        
        assert result_state["need_reroute"] == False, \
            f"need_reroute 应该是 False，实际为: {result_state['need_reroute']}"
        print("  ✓ need_reroute 正确设置为 False")
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, str(e))
        import traceback
        traceback.print_exc()
        raise


def test_route_node_unclear_intent():
    """
    测试用例 3: route_node（意图不明确）
    
    验证：
    - 当用户消息不包含明确的意图关键词时，应该识别为 unclear
    - current_intent 应该设置为 "unclear"
    - current_agent 应该设置为 None
    - need_reroute 应该设置为 False
    """
    test_name = "route_node（意图不明确）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 创建初始状态
        initial_state: RouterState = {
            "messages": [
                HumanMessage(content="你好")
            ],
            "current_intent": None,
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_003",
            "user_id": "test_user_003"
        }
        
        print("\n初始状态:")
        print_state_info(initial_state, "  ")
        print(f"\n用户消息: {initial_state['messages'][0].content}")
        
        # 执行路由节点
        print("\n执行 route_node...")
        result_state = route_node(initial_state)
        
        print("\n路由后的状态:")
        print_state_info(result_state, "  ")
        
        # 验证结果
        print("\n验证结果:")
        assert result_state["current_intent"] == "unclear", \
            f"current_intent 应该是 'unclear'，实际为: {result_state['current_intent']}"
        print("  ✓ current_intent 正确设置为 'unclear'")
        
        assert result_state["current_agent"] is None, \
            f"current_agent 应该是 None，实际为: {result_state['current_agent']}"
        print("  ✓ current_agent 正确设置为 None")
        
        assert result_state["need_reroute"] == False, \
            f"need_reroute 应该是 False，实际为: {result_state['need_reroute']}"
        print("  ✓ need_reroute 正确设置为 False")
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, str(e))
        import traceback
        traceback.print_exc()
        raise


def test_route_node_no_reroute_needed():
    """
    测试用例 4: route_node（已确定智能体，不需要重新路由）
    
    验证：
    - 当已经确定了智能体且 need_reroute 为 False 时，应该直接返回原状态
    - 不应该调用意图识别
    - 状态应该保持不变
    """
    test_name = "route_node（已确定智能体，不需要重新路由）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 创建初始状态（已确定智能体，不需要重新路由）
        initial_state: RouterState = {
            "messages": [
                HumanMessage(content="我想记录血压"),
                AIMessage(content="好的，我来帮您记录血压")
            ],
            "current_intent": "blood_pressure",
            "current_agent": "blood_pressure_agent",
            "need_reroute": False,  # 关键：不需要重新路由
            "session_id": "test_session_004",
            "user_id": "test_user_004"
        }
        
        print("\n初始状态:")
        print_state_info(initial_state, "  ")
        print(f"\n注意: current_agent 已设置，need_reroute 为 False")
        
        # 执行路由节点
        print("\n执行 route_node...")
        result_state = route_node(initial_state)
        
        print("\n路由后的状态:")
        print_state_info(result_state, "  ")
        
        # 验证结果：状态应该完全不变
        print("\n验证结果:")
        assert result_state["current_intent"] == initial_state["current_intent"], \
            f"current_intent 不应该改变，期望: {initial_state['current_intent']}, 实际: {result_state['current_intent']}"
        print(f"  ✓ current_intent 保持不变: {result_state['current_intent']}")
        
        assert result_state["current_agent"] == initial_state["current_agent"], \
            f"current_agent 不应该改变，期望: {initial_state['current_agent']}, 实际: {result_state['current_agent']}"
        print(f"  ✓ current_agent 保持不变: {result_state['current_agent']}")
        
        assert result_state["need_reroute"] == initial_state["need_reroute"], \
            f"need_reroute 不应该改变，期望: {initial_state['need_reroute']}, 实际: {result_state['need_reroute']}"
        print(f"  ✓ need_reroute 保持不变: {result_state['need_reroute']}")
        
        # 验证是同一个对象（说明直接返回了原状态）
        assert result_state is initial_state, \
            "应该直接返回原状态对象（不创建新对象）"
        print("  ✓ 直接返回原状态对象（性能优化）")
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, str(e))
        import traceback
        traceback.print_exc()
        raise


def test_route_node_reroute_needed():
    """
    测试用例 5: route_node（需要重新路由）
    
    验证：
    - 当 need_reroute 为 True 时，即使已经确定了智能体，也应该重新识别意图
    - 应该根据新的意图识别结果更新状态
    """
    test_name = "route_node（需要重新路由）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 创建初始状态（已确定智能体，但需要重新路由）
        initial_state: RouterState = {
            "messages": [
                HumanMessage(content="我想记录血压"),  # 之前的对话是关于血压的
                AIMessage(content="好的，我来帮您记录血压"),
                HumanMessage(content="我想预约内科")  # 新消息是预约意图（最后一条）
            ],
            "current_intent": "blood_pressure",  # 之前是血压意图
            "current_agent": "blood_pressure_agent",  # 之前是血压智能体
            "need_reroute": True,  # 关键：需要重新路由
            "session_id": "test_session_005",
            "user_id": "test_user_005"
        }
        
        print("\n初始状态:")
        print_state_info(initial_state, "  ")
        print(f"\n最后一条用户消息: {initial_state['messages'][-1].content}")
        print(f"注意: 当前智能体是 {initial_state['current_agent']}，但 need_reroute 为 True")
        
        # 保存初始值（因为 route_node 会直接修改传入的 state）
        initial_intent = initial_state["current_intent"]
        initial_agent = initial_state["current_agent"]
        
        # 执行路由节点
        print("\n执行 route_node...")
        result_state = route_node(initial_state)
        
        print("\n路由后的状态:")
        print_state_info(result_state, "  ")
        
        # 验证结果：应该根据新消息重新识别意图
        print("\n验证结果:")
        assert result_state["current_intent"] == "appointment", \
            f"current_intent 应该根据新消息更新为 'appointment'，实际为: {result_state['current_intent']}"
        print("  ✓ current_intent 根据新消息更新为 'appointment'")
        
        assert result_state["current_agent"] == "appointment_agent", \
            f"current_agent 应该更新为 'appointment_agent'，实际为: {result_state['current_agent']}"
        print("  ✓ current_agent 更新为 'appointment_agent'")
        
        assert result_state["need_reroute"] == False, \
            f"need_reroute 应该设置为 False，实际为: {result_state['need_reroute']}"
        print("  ✓ need_reroute 更新为 False")
        
        # 验证状态确实被更新了（与初始值不同）
        assert result_state["current_intent"] != initial_intent, \
            f"current_intent 应该被更新，初始值: {initial_intent}, 当前值: {result_state['current_intent']}"
        assert result_state["current_agent"] != initial_agent, \
            f"current_agent 应该被更新，初始值: {initial_agent}, 当前值: {result_state['current_agent']}"
        print("  ✓ 状态已正确更新")
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, str(e))
        import traceback
        traceback.print_exc()
        raise


def test_route_node_state_update_verification():
    """
    测试用例 6: 状态更新验证
    
    验证：
    - 状态更新的完整性
    - 所有相关字段都被正确更新
    - 不相关的字段保持不变
    - 消息列表不被修改
    """
    test_name = "状态更新验证"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试场景1：从无意图到血压意图
        print("\n场景1: 从无意图到血压意图")
        initial_state_1: RouterState = {
            "messages": [
                HumanMessage(content="查询我的血压记录")
            ],
            "current_intent": None,
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_006_1",
            "user_id": "test_user_006_1"
        }
        
        print("  初始状态:")
        print_state_info(initial_state_1, "    ")
        
        result_state_1 = route_node(initial_state_1)
        
        print("  路由后状态:")
        print_state_info(result_state_1, "    ")
        
        # 验证所有相关字段都被更新
        assert result_state_1["current_intent"] == "blood_pressure", \
            "场景1: current_intent 应该被更新"
        assert result_state_1["current_agent"] == "blood_pressure_agent", \
            "场景1: current_agent 应该被更新"
        assert result_state_1["need_reroute"] == False, \
            "场景1: need_reroute 应该被更新"
        assert result_state_1["session_id"] == initial_state_1["session_id"], \
            "场景1: session_id 不应该改变"
        assert result_state_1["user_id"] == initial_state_1["user_id"], \
            "场景1: user_id 不应该改变"
        assert len(result_state_1["messages"]) == len(initial_state_1["messages"]), \
            "场景1: 消息列表长度不应该改变"
        print("  ✓ 场景1 验证通过")
        
        # 测试场景2：从预约意图到意图不明确
        print("\n场景2: 从预约意图到意图不明确")
        initial_state_2: RouterState = {
            "messages": [
                HumanMessage(content="你好，在吗？")
            ],
            "current_intent": "appointment",
            "current_agent": "appointment_agent",
            "need_reroute": True,
            "session_id": "test_session_006_2",
            "user_id": "test_user_006_2"
        }
        
        print("  初始状态:")
        print_state_info(initial_state_2, "    ")
        
        result_state_2 = route_node(initial_state_2)
        
        print("  路由后状态:")
        print_state_info(result_state_2, "    ")
        
        # 验证状态更新
        assert result_state_2["current_intent"] == "unclear", \
            "场景2: current_intent 应该更新为 'unclear'"
        assert result_state_2["current_agent"] is None, \
            "场景2: current_agent 应该更新为 None"
        assert result_state_2["need_reroute"] == False, \
            "场景2: need_reroute 应该更新为 False"
        print("  ✓ 场景2 验证通过")
        
        # 测试场景3：多条消息的情况
        print("\n场景3: 多条消息的情况")
        initial_state_3: RouterState = {
            "messages": [
                HumanMessage(content="我想记录血压"),
                AIMessage(content="好的，请告诉我您的血压值"),
                HumanMessage(content="收缩压120，舒张压80")
            ],
            "current_intent": None,
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_006_3",
            "user_id": "test_user_006_3"
        }
        
        print("  初始状态:")
        print_state_info(initial_state_3, "    ")
        print(f"  消息数量: {len(initial_state_3['messages'])}")
        
        result_state_3 = route_node(initial_state_3)
        
        print("  路由后状态:")
        print_state_info(result_state_3, "    ")
        
        # 验证：应该根据最后一条用户消息识别意图
        assert result_state_3["current_intent"] == "blood_pressure", \
            "场景3: 应该根据最后一条消息识别为血压意图"
        assert len(result_state_3["messages"]) == len(initial_state_3["messages"]), \
            "场景3: 消息列表不应该被修改"
        print("  ✓ 场景3 验证通过")
        
        print("\n所有场景验证通过:")
        print("  ✓ 状态更新完整性验证通过")
        print("  ✓ 相关字段正确更新")
        print("  ✓ 不相关字段保持不变")
        print("  ✓ 消息列表不被修改")
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, str(e))
        import traceback
        traceback.print_exc()
        raise


def run_all_tests():
    """运行所有测试"""
    print("="*60)
    print("路由节点测试")
    print("="*60)
    print()
    
    try:
        test_route_node_blood_pressure_intent()
        test_route_node_appointment_intent()
        test_route_node_unclear_intent()
        test_route_node_no_reroute_needed()
        test_route_node_reroute_needed()
        # 重点用例-全链路组合
        test_route_node_state_update_verification()
    except Exception as e:
        print(f"\n❌ 测试执行过程中发生异常: {e}")
        import traceback
        traceback.print_exc()
    
    # 打印测试总结
    success = test_result.summary()
    
    # 返回退出码
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
