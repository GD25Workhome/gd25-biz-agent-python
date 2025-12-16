"""
路由状态测试
测试 RouterState 和 IntentResult 数据结构

运行方式：
==========
# 直接运行测试文件
python cursor_test/M1_test/domain/test_router_state.py

# 或者在项目根目录运行
python -m cursor_test.M1_test.domain.test_router_state
"""
import sys
import os
import json
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到 Python 路径
# test_router_state.py 位于: cursor_test/M1_test/domain/test_router_state.py
# 项目根目录: cursor_test/M1_test/domain/../../../
test_file_path = Path(__file__).resolve()
project_root = test_file_path.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from domain.router.state import RouterState, IntentResult
from pydantic import ValidationError


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


def test_router_state_type_definition():
    """
    测试用例 1: RouterState 类型定义验证
    
    验证：
    - RouterState 可以正确创建
    - 所有必需字段都存在
    - 字段类型正确
    """
    test_name = "RouterState 类型定义验证"
    
    try:
        # 创建测试消息
        messages = [
            HumanMessage(content="我想记录血压"),
            AIMessage(content="好的，我来帮您记录血压")
        ]
        
        # 创建 RouterState 实例
        state: RouterState = {
            "messages": messages,
            "current_intent": "blood_pressure",
            "current_agent": "blood_pressure_agent",
            "need_reroute": False,
            "session_id": "test_session_001",
            "user_id": "test_user_001"
        }
        
        # 验证必需字段存在
        assert "messages" in state, "messages 字段缺失"
        assert "current_intent" in state, "current_intent 字段缺失"
        assert "current_agent" in state, "current_agent 字段缺失"
        assert "need_reroute" in state, "need_reroute 字段缺失"
        assert "session_id" in state, "session_id 字段缺失"
        assert "user_id" in state, "user_id 字段缺失"
        
        # 验证字段类型
        assert isinstance(state["messages"], list), "messages 应该是列表类型"
        assert all(isinstance(msg, BaseMessage) for msg in state["messages"]), "messages 中的元素应该是 BaseMessage 类型"
        assert state["current_intent"] is None or isinstance(state["current_intent"], str), "current_intent 应该是字符串或 None"
        assert state["current_agent"] is None or isinstance(state["current_agent"], str), "current_agent 应该是字符串或 None"
        assert isinstance(state["need_reroute"], bool), "need_reroute 应该是布尔类型"
        assert isinstance(state["session_id"], str), "session_id 应该是字符串类型"
        assert isinstance(state["user_id"], str), "user_id 应该是字符串类型"
        
        # 验证可选字段可以为 None
        state_with_none: RouterState = {
            "messages": [],
            "current_intent": None,
            "current_agent": None,
            "need_reroute": True,
            "session_id": "test_session_002",
            "user_id": "test_user_002"
        }
        assert state_with_none["current_intent"] is None, "current_intent 应该可以为 None"
        assert state_with_none["current_agent"] is None, "current_agent 应该可以为 None"
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, str(e))
        raise


def test_intent_result_normal_case():
    """
    测试用例 2: IntentResult 模型验证（正常情况）
    
    验证：
    - IntentResult 可以正确创建
    - 所有字段都可以正常设置
    - 可选字段可以省略
    """
    test_name = "IntentResult 模型验证（正常情况）"
    
    try:
        # 测试完整字段
        result1 = IntentResult(
            intent_type="blood_pressure",
            confidence=0.95,
            entities={"systolic": 120, "diastolic": 80},
            need_clarification=False,
            reasoning="检测到血压相关关键词"
        )
        
        assert result1.intent_type == "blood_pressure", "intent_type 设置错误"
        assert result1.confidence == 0.95, "confidence 设置错误"
        assert result1.entities == {"systolic": 120, "diastolic": 80}, "entities 设置错误"
        assert result1.need_clarification == False, "need_clarification 设置错误"
        assert result1.reasoning == "检测到血压相关关键词", "reasoning 设置错误"
        
        # 测试省略可选字段 reasoning
        result2 = IntentResult(
            intent_type="appointment",
            confidence=0.85,
            entities={"department": "内科"},
            need_clarification=True
        )
        
        assert result2.intent_type == "appointment", "intent_type 设置错误"
        assert result2.confidence == 0.85, "confidence 设置错误"
        assert result2.reasoning is None, "reasoning 应该默认为 None"
        
        # 测试 unclear 意图
        result3 = IntentResult(
            intent_type="unclear",
            confidence=0.3,
            entities={},
            need_clarification=True,
            reasoning="无法明确识别用户意图"
        )
        
        assert result3.intent_type == "unclear", "intent_type 设置错误"
        assert result3.confidence == 0.3, "confidence 设置错误"
        assert result3.need_clarification == True, "need_clarification 设置错误"
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, str(e))
        raise


def test_intent_result_boundary_conditions():
    """
    测试用例 3: IntentResult 模型验证（边界条件：confidence 0.0-1.0）
    
    验证：
    - confidence 在有效范围内（0.0-1.0）可以正常创建
    - confidence 超出范围（< 0.0 或 > 1.0）应该被 Pydantic Field 约束拒绝并抛出 ValidationError
    """
    test_name = "IntentResult 模型验证（边界条件：confidence 0.0-1.0）"
    
    try:
        # 测试边界值 0.0
        result_min = IntentResult(
            intent_type="unclear",
            confidence=0.0,
            entities={},
            need_clarification=True
        )
        assert result_min.confidence == 0.0, "confidence 应该可以设置为 0.0"
        
        # 测试边界值 1.0
        result_max = IntentResult(
            intent_type="blood_pressure",
            confidence=1.0,
            entities={},
            need_clarification=False
        )
        assert result_max.confidence == 1.0, "confidence 应该可以设置为 1.0"
        
        # 测试中间值
        result_mid = IntentResult(
            intent_type="appointment",
            confidence=0.5,
            entities={},
            need_clarification=False
        )
        assert result_mid.confidence == 0.5, "confidence 应该可以设置为 0.5"
        
        # 测试小数精度
        result_decimal = IntentResult(
            intent_type="blood_pressure",
            confidence=0.123456789,
            entities={},
            need_clarification=False
        )
        assert result_decimal.confidence == 0.123456789, "confidence 应该支持小数精度"
        
        # 测试超出范围的值，应该被 Pydantic 验证拒绝
        # 测试负数（应该抛出 ValidationError）
        try:
            result_negative = IntentResult(
                intent_type="unclear",
                confidence=-0.1,
                entities={},
                need_clarification=True
            )
            # 如果创建成功，说明没有范围验证
            test_result.add_fail(test_name, "confidence 为负数时应该抛出 ValidationError，但创建成功了")
            raise AssertionError("confidence 为负数时应该抛出 ValidationError")
        except ValidationError as e:
            # 验证错误是预期的
            assert "confidence" in str(e).lower() or "greater than or equal" in str(e).lower(), \
                f"ValidationError 应该与 confidence 字段相关: {e}"
            print("✓ confidence 为负数时正确抛出 ValidationError")
        
        # 测试大于 1.0 的值（应该抛出 ValidationError）
        try:
            result_over = IntentResult(
                intent_type="blood_pressure",
                confidence=1.5,
                entities={},
                need_clarification=False
            )
            # 如果创建成功，说明没有范围验证
            test_result.add_fail(test_name, "confidence 大于 1.0 时应该抛出 ValidationError，但创建成功了")
            raise AssertionError("confidence 大于 1.0 时应该抛出 ValidationError")
        except ValidationError as e:
            # 验证错误是预期的
            assert "confidence" in str(e).lower() or "less than or equal" in str(e).lower(), \
                f"ValidationError 应该与 confidence 字段相关: {e}"
            print("✓ confidence 大于 1.0 时正确抛出 ValidationError")
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, str(e))
        raise


def test_intent_result_serialization():
    """
    测试用例 4: IntentResult 序列化/反序列化
    
    验证：
    - IntentResult 可以序列化为 JSON
    - IntentResult 可以从 JSON 反序列化
    - 序列化和反序列化后数据一致
    """
    test_name = "IntentResult 序列化/反序列化"
    
    try:
        # 创建测试对象
        original = IntentResult(
            intent_type="blood_pressure",
            confidence=0.95,
            entities={"systolic": 120, "diastolic": 80, "unit": "mmHg"},
            need_clarification=False,
            reasoning="检测到血压相关关键词：血压、收缩压、舒张压"
        )
        
        # 测试 Pydantic 的序列化方法
        # 方法 1: model_dump() - 转换为字典
        dict_data = original.model_dump()
        assert isinstance(dict_data, dict), "model_dump() 应该返回字典"
        assert dict_data["intent_type"] == "blood_pressure", "序列化后 intent_type 应该一致"
        assert dict_data["confidence"] == 0.95, "序列化后 confidence 应该一致"
        assert dict_data["entities"] == {"systolic": 120, "diastolic": 80, "unit": "mmHg"}, "序列化后 entities 应该一致"
        assert dict_data["need_clarification"] == False, "序列化后 need_clarification 应该一致"
        assert dict_data["reasoning"] == "检测到血压相关关键词：血压、收缩压、舒张压", "序列化后 reasoning 应该一致"
        
        # 方法 2: model_dump_json() - 转换为 JSON 字符串
        json_str = original.model_dump_json()
        assert isinstance(json_str, str), "model_dump_json() 应该返回字符串"
        
        # 验证 JSON 字符串可以解析
        parsed_dict = json.loads(json_str)
        assert parsed_dict["intent_type"] == "blood_pressure", "JSON 解析后 intent_type 应该一致"
        assert parsed_dict["confidence"] == 0.95, "JSON 解析后 confidence 应该一致"
        
        # 方法 3: 从字典反序列化
        restored = IntentResult(**dict_data)
        assert restored.intent_type == original.intent_type, "反序列化后 intent_type 应该一致"
        assert restored.confidence == original.confidence, "反序列化后 confidence 应该一致"
        assert restored.entities == original.entities, "反序列化后 entities 应该一致"
        assert restored.need_clarification == original.need_clarification, "反序列化后 need_clarification 应该一致"
        assert restored.reasoning == original.reasoning, "反序列化后 reasoning 应该一致"
        
        # 方法 4: 从 JSON 字符串反序列化
        restored_from_json = IntentResult.model_validate_json(json_str)
        assert restored_from_json.intent_type == original.intent_type, "从 JSON 反序列化后 intent_type 应该一致"
        assert restored_from_json.confidence == original.confidence, "从 JSON 反序列化后 confidence 应该一致"
        assert restored_from_json.entities == original.entities, "从 JSON 反序列化后 entities 应该一致"
        
        # 测试可选字段为 None 的情况
        original_no_reasoning = IntentResult(
            intent_type="appointment",
            confidence=0.85,
            entities={"department": "内科"},
            need_clarification=True
        )
        
        dict_data_no_reasoning = original_no_reasoning.model_dump()
        assert "reasoning" in dict_data_no_reasoning, "reasoning 字段应该在序列化结果中"
        assert dict_data_no_reasoning["reasoning"] is None, "reasoning 应该为 None"
        
        restored_no_reasoning = IntentResult(**dict_data_no_reasoning)
        assert restored_no_reasoning.reasoning is None, "反序列化后 reasoning 应该仍为 None"
        
        # 测试复杂 entities
        complex_original = IntentResult(
            intent_type="blood_pressure",
            confidence=0.9,
            entities={
                "systolic": 120,
                "diastolic": 80,
                "timestamp": "2024-01-01T10:00:00",
                "metadata": {
                    "source": "user_input",
                    "confidence": 0.9
                }
            },
            need_clarification=False,
            reasoning="复杂实体测试"
        )
        
        complex_dict = complex_original.model_dump()
        complex_restored = IntentResult(**complex_dict)
        assert complex_restored.entities == complex_original.entities, "复杂 entities 应该正确序列化和反序列化"
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, str(e))
        raise


def run_all_tests():
    """运行所有测试"""
    print("="*60)
    print("路由状态测试")
    print("="*60)
    print()
    
    try:
        test_router_state_type_definition()
        test_intent_result_normal_case()
        test_intent_result_boundary_conditions()
        test_intent_result_serialization()
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
