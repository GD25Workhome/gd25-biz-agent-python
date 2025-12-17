"""
路由工具测试
测试 identify_intent 函数的意图识别逻辑

运行方式：
==========
# 直接运行测试文件
python cursor_test/M1_test/domain/test_router_tools.py

# 或者在项目根目录运行
python -m cursor_test.M1_test.domain.test_router_tools
"""
import sys
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到 Python 路径
# test_router_tools.py 位于: cursor_test/M1_test/domain/test_router_tools.py
# 项目根目录: cursor_test/M1_test/domain/../../../
test_file_path = Path(__file__).resolve()
project_root = test_file_path.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain_core.messages import HumanMessage, BaseMessage
from domain.router.tools.router_tools import identify_intent


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


def test_identify_intent_blood_pressure():
    """
    测试用例 1: identify_intent（血压意图识别）
    
    验证：
    - 当用户消息包含血压相关关键词时，能够正确识别为血压意图
    - intent_type 应该为 "blood_pressure"
    - confidence 应该在合理范围内
    - need_clarification 应该为 False
    """
    test_name = "identify_intent（血压意图识别）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试数据：血压意图
        test_cases = [
            "我想记录血压，收缩压120，舒张压80",
            "查询我的血压记录",
            "更新血压数据"
        ]
        
        for i, message_text in enumerate(test_cases, 1):
            print(f"\n测试子用例 {i}: {message_text}")
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            # 验证结果结构
            assert isinstance(result, dict), "返回结果应该是字典类型"
            assert "intent_type" in result, "结果应该包含 intent_type 字段"
            assert "confidence" in result, "结果应该包含 confidence 字段"
            assert "need_clarification" in result, "结果应该包含 need_clarification 字段"
            
            # 验证意图类型
            assert result["intent_type"] == "blood_pressure", \
                f"意图类型应该是 'blood_pressure'，实际为 '{result['intent_type']}'"
            
            # 验证置信度范围
            assert 0.0 <= result["confidence"] <= 1.0, \
                f"置信度应该在 0.0-1.0 之间，实际为 {result['confidence']}"
            
            # 验证不需要澄清
            assert result["need_clarification"] == False, \
                "血压意图应该不需要澄清"
            
            print(f"  ✅ 意图类型: {result['intent_type']}")
            print(f"  ✅ 置信度: {result['confidence']}")
            print(f"  ✅ 需要澄清: {result['need_clarification']}")
            print(f"  ✅ 识别理由: {result.get('reasoning', 'N/A')}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_appointment():
    """
    测试用例 2: identify_intent（预约意图识别）
    
    验证：
    - 当用户消息包含预约相关关键词时，能够正确识别为预约意图
    - intent_type 应该为 "appointment"
    - confidence 应该在合理范围内
    - need_clarification 应该为 False
    """
    test_name = "identify_intent（预约意图识别）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试数据：预约意图
        test_cases = [
            "我想预约内科",
            "查询我的预约",
            "取消预约"
        ]
        
        for i, message_text in enumerate(test_cases, 1):
            print(f"\n测试子用例 {i}: {message_text}")
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            # 验证结果结构
            assert isinstance(result, dict), "返回结果应该是字典类型"
            assert "intent_type" in result, "结果应该包含 intent_type 字段"
            
            # 验证意图类型
            assert result["intent_type"] == "appointment", \
                f"意图类型应该是 'appointment'，实际为 '{result['intent_type']}'"
            
            # 验证置信度范围
            assert 0.0 <= result["confidence"] <= 1.0, \
                f"置信度应该在 0.0-1.0 之间，实际为 {result['confidence']}"
            
            # 验证不需要澄清
            assert result["need_clarification"] == False, \
                "预约意图应该不需要澄清"
            
            print(f"  ✅ 意图类型: {result['intent_type']}")
            print(f"  ✅ 置信度: {result['confidence']}")
            print(f"  ✅ 需要澄清: {result['need_clarification']}")
            print(f"  ✅ 识别理由: {result.get('reasoning', 'N/A')}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_unclear():
    """
    测试用例 3: identify_intent（意图不明确）
    
    验证：
    - 当用户消息不包含明确的意图关键词时，应该识别为 unclear
    - intent_type 应该为 "unclear"
    - need_clarification 应该为 True
    """
    test_name = "identify_intent（意图不明确）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试数据：意图不明确
        test_cases = [
            "你好",
            "今天天气怎么样"
        ]
        
        for i, message_text in enumerate(test_cases, 1):
            print(f"\n测试子用例 {i}: {message_text}")
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            # 验证结果结构
            assert isinstance(result, dict), "返回结果应该是字典类型"
            assert "intent_type" in result, "结果应该包含 intent_type 字段"
            
            # 验证意图类型
            assert result["intent_type"] == "unclear", \
                f"意图类型应该是 'unclear'，实际为 '{result['intent_type']}'"
            
            # 验证需要澄清
            assert result["need_clarification"] == True, \
                "意图不明确时应该需要澄清"
            
            print(f"  ✅ 意图类型: {result['intent_type']}")
            print(f"  ✅ 置信度: {result['confidence']}")
            print(f"  ✅ 需要澄清: {result['need_clarification']}")
            print(f"  ✅ 识别理由: {result.get('reasoning', 'N/A')}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_empty_messages():
    """
    测试用例 4: identify_intent（空消息列表）
    
    验证：
    - 当消息列表为空时，应该返回 unclear 意图
    - need_clarification 应该为 True
    - confidence 应该为 0.0
    """
    test_name = "identify_intent（空消息列表）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试空消息列表
        messages = []
        result = identify_intent.invoke({"messages": messages})
        
        # 验证结果结构
        assert isinstance(result, dict), "返回结果应该是字典类型"
        assert "intent_type" in result, "结果应该包含 intent_type 字段"
        
        # 验证意图类型
        assert result["intent_type"] == "unclear", \
            f"空消息列表时意图类型应该是 'unclear'，实际为 '{result['intent_type']}'"
        
        # 验证置信度
        assert result["confidence"] == 0.0, \
            f"空消息列表时置信度应该是 0.0，实际为 {result['confidence']}"
        
        # 验证需要澄清
        assert result["need_clarification"] == True, \
            "空消息列表时应该需要澄清"
        
        print(f"  ✅ 意图类型: {result['intent_type']}")
        print(f"  ✅ 置信度: {result['confidence']}")
        print(f"  ✅ 需要澄清: {result['need_clarification']}")
        print(f"  ✅ 识别理由: {result.get('reasoning', 'N/A')}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_multiple_keywords():
    """
    测试用例 5: identify_intent（多个关键词匹配）
    
    验证：
    - 当消息包含多个关键词时，置信度应该相应提高
    - 多个关键词匹配应该增加置信度
    """
    test_name = "identify_intent（多个关键词匹配）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试单个关键词
        single_keyword_message = "我想记录血压"
        messages_single = [HumanMessage(content=single_keyword_message)]
        result_single = identify_intent.invoke({"messages": messages_single})
        
        print(f"\n单个关键词: {single_keyword_message}")
        print(f"  置信度: {result_single['confidence']}")
        
        # 测试多个关键词
        multiple_keywords_message = "我想记录血压，收缩压120，舒张压80，心率正常"
        messages_multiple = [HumanMessage(content=multiple_keywords_message)]
        result_multiple = identify_intent.invoke({"messages": messages_multiple})
        
        print(f"\n多个关键词: {multiple_keywords_message}")
        print(f"  置信度: {result_multiple['confidence']}")
        
        # 验证多个关键词的置信度应该大于或等于单个关键词
        # 注意：根据实现，置信度计算公式是 min(0.9, 0.5 + score * 0.1)
        # 所以多个关键词的置信度应该更高
        assert result_multiple["intent_type"] == "blood_pressure", \
            "多个关键词应该识别为血压意图"
        
        assert result_multiple["confidence"] >= result_single["confidence"], \
            f"多个关键词的置信度({result_multiple['confidence']})应该大于等于单个关键词的置信度({result_single['confidence']})"
        
        print(f"  ✅ 单个关键词置信度: {result_single['confidence']}")
        print(f"  ✅ 多个关键词置信度: {result_multiple['confidence']}")
        print(f"  ✅ 置信度提升: {result_multiple['confidence'] - result_single['confidence']:.2f}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_confidence_calculation():
    """
    测试用例 6: identify_intent（置信度计算）
    
    验证：
    - 置信度应该在 0.0-1.0 范围内
    - 置信度计算逻辑正确
    - 不同匹配数量的关键词对应不同的置信度
    """
    test_name = "identify_intent（置信度计算）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试不同数量的关键词匹配
        test_cases = [
            ("血压", 1),  # 1个关键词
            ("血压，收缩压", 2),  # 2个关键词
            ("血压，收缩压，舒张压", 3),  # 3个关键词
        ]
        
        previous_confidence = 0.0
        
        for i, (message_text, expected_keywords) in enumerate(test_cases, 1):
            print(f"\n测试子用例 {i}: {message_text} (预期匹配 {expected_keywords} 个关键词)")
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            # 验证置信度范围
            assert 0.0 <= result["confidence"] <= 1.0, \
                f"置信度应该在 0.0-1.0 之间，实际为 {result['confidence']}"
            
            # 验证置信度应该递增（或至少不递减）
            if i > 1:
                assert result["confidence"] >= previous_confidence, \
                    f"更多关键词匹配时，置信度应该增加或保持不变。当前: {result['confidence']}, 之前: {previous_confidence}"
            
            # 验证置信度计算公式：min(0.9, 0.5 + score * 0.1)
            expected_confidence = min(0.9, 0.5 + expected_keywords * 0.1)
            assert abs(result["confidence"] - expected_confidence) < 0.01, \
                f"置信度计算不正确。预期: {expected_confidence}, 实际: {result['confidence']}"
            
            print(f"  ✅ 匹配关键词数: {expected_keywords}")
            print(f"  ✅ 置信度: {result['confidence']} (预期: {expected_confidence})")
            
            previous_confidence = result["confidence"]
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_edge_cases():
    """
    测试用例 7: identify_intent（边界条件：大小写、标点符号）
    
    验证：
    - 大小写不敏感：大写、小写、混合大小写都能正确识别
    - 标点符号不影响识别：包含各种标点符号的消息仍能正确识别
    """
    test_name = "identify_intent（边界条件：大小写、标点符号）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试大小写不敏感
        print("\n--- 测试大小写不敏感 ---")
        case_tests = [
            ("我想记录血压", "小写"),
            ("我想记录血压", "大写"),
            ("我想记录血压", "混合大小写"),
        ]
        
        # 由于实现中使用了 .lower()，所以大小写应该不影响
        for message_text, case_type in case_tests:
            if case_type == "大写":
                message_text = message_text.upper()
            elif case_type == "混合大小写":
                message_text = "我想记录血圧"  # 注意：这里用全角字符测试
                # 实际测试混合大小写
                message_text = "我想记录血Ya"
            
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            print(f"\n{case_type}: {message_text}")
            print(f"  意图类型: {result['intent_type']}")
            
            # 验证小写和大写都能识别（因为实现中使用了 .lower()）
            if case_type in ["小写", "大写"]:
                assert result["intent_type"] == "blood_pressure", \
                    f"{case_type}消息应该能识别为血压意图"
        
        # 测试标点符号
        print("\n--- 测试标点符号 ---")
        punctuation_tests = [
            "我想记录血压，收缩压120，舒张压80。",
            "我想记录血压！收缩压120；舒张压80？",
            "我想记录血压（收缩压120，舒张压80）",
            "我想记录血压【收缩压120】",
        ]
        
        for message_text in punctuation_tests:
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            print(f"\n消息: {message_text}")
            print(f"  意图类型: {result['intent_type']}")
            
            # 验证标点符号不影响识别
            assert result["intent_type"] == "blood_pressure", \
                f"包含标点符号的消息应该能识别为血压意图: {message_text}"
        
        # 测试预约意图的大小写和标点符号
        print("\n--- 测试预约意图的边界条件 ---")
        appointment_tests = [
            "我想预约内科",
            "我想预约内科！",
            "我想预约内科？",
            "我想预约内科。",
        ]
        
        for message_text in appointment_tests:
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            print(f"\n消息: {message_text}")
            print(f"  意图类型: {result['intent_type']}")
            
            assert result["intent_type"] == "appointment", \
                f"预约消息应该能识别为预约意图: {message_text}"
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def main():
    """运行所有测试"""
    print("="*60)
    print("路由工具测试 - identify_intent 函数")
    print("="*60)
    
    # 运行所有测试用例
    test_identify_intent_blood_pressure()
    test_identify_intent_appointment()
    test_identify_intent_unclear()
    test_identify_intent_empty_messages()
    test_identify_intent_multiple_keywords()
    test_identify_intent_confidence_calculation()
    test_identify_intent_edge_cases()
    
    # 打印测试总结
    success = test_result.summary()
    
    # 返回退出码
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
