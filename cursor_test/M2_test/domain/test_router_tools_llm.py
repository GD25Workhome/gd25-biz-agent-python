"""
路由工具测试 - LLM 版本意图识别
测试 identify_intent 函数的 LLM 意图识别逻辑

运行方式：
==========
# 直接运行测试文件
python cursor_test/M2_test/domain/test_router_tools_llm.py

# 或者在项目根目录运行
python -m cursor_test.M2_test.domain.test_router_tools_llm
"""
import sys
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到 Python 路径
test_file_path = Path(__file__).resolve()
project_root = test_file_path.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
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


def test_identify_intent_blood_pressure_basic():
    """
    测试用例 1: identify_intent（血压意图识别 - 基础场景）
    
    验证：
    - 当用户消息包含血压相关关键词时，能够正确识别为血压意图
    - intent_type 应该为 "blood_pressure"
    - confidence 应该在合理范围内（> 0.8）
    - need_clarification 应该为 False
    """
    test_name = "identify_intent（血压意图识别 - 基础场景）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试数据：血压意图
        test_cases = [
            "我想记录血压，收缩压120，舒张压80",
            "查询我的血压记录",
            "更新血压数据",
            "我的收缩压是120，舒张压是80",
            "帮我记录一下血压",
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
            assert "entities" in result, "结果应该包含 entities 字段"
            assert "reasoning" in result, "结果应该包含 reasoning 字段"
            
            # 验证意图类型
            assert result["intent_type"] == "blood_pressure", \
                f"意图类型应该是 'blood_pressure'，实际为 '{result['intent_type']}'"
            
            # 验证置信度范围
            assert 0.0 <= result["confidence"] <= 1.0, \
                f"置信度应该在 0.0-1.0 之间，实际为 {result['confidence']}"
            
            # 验证置信度应该较高（LLM 识别应该更准确）
            assert result["confidence"] >= 0.7, \
                f"明确的血压意图置信度应该 >= 0.7，实际为 {result['confidence']}"
            
            # 验证不需要澄清（如果置信度足够高）
            if result["confidence"] >= 0.8:
                assert result["need_clarification"] == False, \
                    f"高置信度({result['confidence']})时应该不需要澄清"
            
            print(f"  ✅ 意图类型: {result['intent_type']}")
            print(f"  ✅ 置信度: {result['confidence']}")
            print(f"  ✅ 需要澄清: {result['need_clarification']}")
            print(f"  ✅ 识别理由: {result.get('reasoning', 'N/A')[:100]}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_appointment_basic():
    """
    测试用例 2: identify_intent（预约意图识别 - 基础场景）
    
    验证：
    - 当用户消息包含预约相关关键词时，能够正确识别为预约意图
    - intent_type 应该为 "appointment"
    - confidence 应该在合理范围内（> 0.8）
    - need_clarification 应该为 False
    """
    test_name = "identify_intent（预约意图识别 - 基础场景）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试数据：预约意图
        test_cases = [
            "我想预约内科",
            "查询我的预约",
            "取消预约",
            "帮我挂个号",
            "我想预约复诊",
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
            
            # 验证置信度应该较高
            assert result["confidence"] >= 0.7, \
                f"明确的预约意图置信度应该 >= 0.7，实际为 {result['confidence']}"
            
            # 验证不需要澄清（如果置信度足够高）
            if result["confidence"] >= 0.8:
                assert result["need_clarification"] == False, \
                    f"高置信度({result['confidence']})时应该不需要澄清"
            
            print(f"  ✅ 意图类型: {result['intent_type']}")
            print(f"  ✅ 置信度: {result['confidence']}")
            print(f"  ✅ 需要澄清: {result['need_clarification']}")
            print(f"  ✅ 识别理由: {result.get('reasoning', 'N/A')[:100]}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_unclear_basic():
    """
    测试用例 3: identify_intent（意图不明确 - 基础场景）
    
    验证：
    - 当用户消息不包含明确的意图关键词时，应该识别为 unclear
    - intent_type 应该为 "unclear"
    - need_clarification 应该为 True
    - confidence 应该较低（< 0.8）
    """
    test_name = "identify_intent（意图不明确 - 基础场景）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试数据：意图不明确
        test_cases = [
            "你好",
            "在吗",
            "有什么功能",
            "谢谢",
            "今天天气怎么样",
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
            
            # 验证置信度应该较低
            assert result["confidence"] < 0.8, \
                f"不明确的意图置信度应该 < 0.8，实际为 {result['confidence']}"
            
            print(f"  ✅ 意图类型: {result['intent_type']}")
            print(f"  ✅ 置信度: {result['confidence']}")
            print(f"  ✅ 需要澄清: {result['need_clarification']}")
            print(f"  ✅ 识别理由: {result.get('reasoning', 'N/A')[:100]}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_with_conversation_history():
    """
    测试用例 4: identify_intent（带对话历史的意图识别）
    
    验证：
    - 能够利用对话历史上下文进行意图识别
    - 短消息在对话历史上下文中能够正确识别
    - 对话历史中的意图信息能够影响识别结果
    """
    test_name = "identify_intent（带对话历史的意图识别）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试场景 1: 血压对话历史
        print("\n--- 测试场景 1: 血压对话历史 ---")
        messages_bp = [
            HumanMessage(content="我想记录血压"),
            AIMessage(content="好的，请告诉我您的收缩压和舒张压"),
            HumanMessage(content="120和80"),  # 短消息，依赖上下文
        ]
        result_bp = identify_intent.invoke({"messages": messages_bp})
        
        print(f"对话历史: 血压相关")
        print(f"当前消息: 120和80")
        print(f"  意图类型: {result_bp['intent_type']}")
        print(f"  置信度: {result_bp['confidence']}")
        
        # 在血压对话上下文中，短消息应该识别为血压意图
        assert result_bp["intent_type"] in ["blood_pressure", "unclear"], \
            f"在血压对话上下文中，短消息应该识别为血压意图或unclear，实际为 {result_bp['intent_type']}"
        
        # 测试场景 2: 预约对话历史
        print("\n--- 测试场景 2: 预约对话历史 ---")
        messages_apt = [
            HumanMessage(content="我想预约"),
            AIMessage(content="好的，请告诉我您想预约哪个科室"),
            HumanMessage(content="内科"),  # 短消息，依赖上下文
        ]
        result_apt = identify_intent.invoke({"messages": messages_apt})
        
        print(f"对话历史: 预约相关")
        print(f"当前消息: 内科")
        print(f"  意图类型: {result_apt['intent_type']}")
        print(f"  置信度: {result_apt['confidence']}")
        
        # 在预约对话上下文中，短消息应该识别为预约意图
        assert result_apt["intent_type"] in ["appointment", "unclear"], \
            f"在预约对话上下文中，短消息应该识别为预约意图或unclear，实际为 {result_apt['intent_type']}"
        
        # 测试场景 3: 无上下文短消息
        print("\n--- 测试场景 3: 无上下文短消息 ---")
        messages_short = [
            HumanMessage(content="120和80"),  # 无上下文
        ]
        result_short = identify_intent.invoke({"messages": messages_short})
        
        print(f"对话历史: 无")
        print(f"当前消息: 120和80")
        print(f"  意图类型: {result_short['intent_type']}")
        print(f"  置信度: {result_short['confidence']}")
        
        # 无上下文时，短消息应该识别为 unclear
        assert result_short["intent_type"] == "unclear", \
            f"无上下文时，短消息应该识别为unclear，实际为 {result_short['intent_type']}"
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_complex_scenarios():
    """
    测试用例 5: identify_intent（复杂场景）
    
    验证：
    - 能够处理复杂的自然语言表达
    - 能够识别隐含的意图
    - 能够处理多意图混合的情况（按优先级选择）
    """
    test_name = "identify_intent（复杂场景）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试场景 1: 隐含的血压意图
        print("\n--- 测试场景 1: 隐含的血压意图 ---")
        implicit_bp_cases = [
            "我今天的血压有点高",
            "最近血压不太稳定",
            "医生让我每天测血压",
        ]
        
        for message_text in implicit_bp_cases:
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            print(f"\n消息: {message_text}")
            print(f"  意图类型: {result['intent_type']}")
            print(f"  置信度: {result['confidence']}")
            
            # 应该识别为血压意图
            assert result["intent_type"] == "blood_pressure", \
                f"隐含的血压意图应该被识别，实际为 {result['intent_type']}"
        
        # 测试场景 2: 隐含的预约意图
        print("\n--- 测试场景 2: 隐含的预约意图 ---")
        implicit_apt_cases = [
            "我想去看医生",
            "需要安排一下复诊时间",
            "什么时候可以看病",
        ]
        
        for message_text in implicit_apt_cases:
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            print(f"\n消息: {message_text}")
            print(f"  意图类型: {result['intent_type']}")
            print(f"  置信度: {result['confidence']}")
            
            # 应该识别为预约意图
            assert result["intent_type"] == "appointment", \
                f"隐含的预约意图应该被识别，实际为 {result['intent_type']}"
        
        # 测试场景 3: 多意图混合（预约优先级更高）
        print("\n--- 测试场景 3: 多意图混合 ---")
        mixed_cases = [
            "我想预约复诊，顺便记录一下血压",
            "挂号后帮我记录血压",
        ]
        
        for message_text in mixed_cases:
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            print(f"\n消息: {message_text}")
            print(f"  意图类型: {result['intent_type']}")
            print(f"  置信度: {result['confidence']}")
            
            # 根据优先级，应该识别为预约意图
            assert result["intent_type"] == "appointment", \
                f"多意图混合时应该按优先级选择预约，实际为 {result['intent_type']}"
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_edge_cases():
    """
    测试用例 6: identify_intent（边界情况）
    
    验证：
    - 空消息列表
    - 空字符串消息
    - 超长消息
    - 特殊字符
    - 表情符号
    """
    test_name = "identify_intent（边界情况）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试场景 1: 空消息列表
        print("\n--- 测试场景 1: 空消息列表 ---")
        messages_empty = []
        result_empty = identify_intent.invoke({"messages": messages_empty})
        
        assert isinstance(result_empty, dict), "应该返回字典"
        assert result_empty["intent_type"] == "unclear", \
            f"空消息列表应该返回unclear，实际为 {result_empty['intent_type']}"
        assert result_empty["confidence"] == 0.0, \
            f"空消息列表置信度应该为0.0，实际为 {result_empty['confidence']}"
        assert result_empty["need_clarification"] == True, \
            "空消息列表应该需要澄清"
        
        print(f"  ✅ 空消息列表处理正确")
        
        # 测试场景 2: 空字符串消息
        print("\n--- 测试场景 2: 空字符串消息 ---")
        messages_empty_str = [HumanMessage(content="")]
        result_empty_str = identify_intent.invoke({"messages": messages_empty_str})
        
        assert isinstance(result_empty_str, dict), "应该返回字典"
        assert result_empty_str["intent_type"] == "unclear", \
            f"空字符串消息应该返回unclear，实际为 {result_empty_str['intent_type']}"
        
        print(f"  ✅ 空字符串消息处理正确")
        
        # 测试场景 3: 只包含空格的消息
        print("\n--- 测试场景 3: 只包含空格的消息 ---")
        messages_space = [HumanMessage(content="   ")]
        result_space = identify_intent.invoke({"messages": messages_space})
        
        assert isinstance(result_space, dict), "应该返回字典"
        assert result_space["intent_type"] == "unclear", \
            f"只包含空格的消息应该返回unclear，实际为 {result_space['intent_type']}"
        
        print(f"  ✅ 只包含空格的消息处理正确")
        
        # 测试场景 4: 特殊字符
        print("\n--- 测试场景 4: 特殊字符 ---")
        special_chars_cases = [
            "我想记录血压！@#￥%……&*（）",
            "预约***复诊###",
        ]
        
        for message_text in special_chars_cases:
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            print(f"\n消息: {message_text}")
            print(f"  意图类型: {result['intent_type']}")
            
            # 应该能够识别意图（忽略特殊字符）
            assert result["intent_type"] in ["blood_pressure", "appointment", "unclear"], \
                f"包含特殊字符的消息应该能够识别意图，实际为 {result['intent_type']}"
        
        # 测试场景 5: 表情符号
        print("\n--- 测试场景 5: 表情符号 ---")
        emoji_cases = [
            "我想记录血压😊",
            "预约复诊👍",
        ]
        
        for message_text in emoji_cases:
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            print(f"\n消息: {message_text}")
            print(f"  意图类型: {result['intent_type']}")
            
            # 应该能够识别意图（忽略表情符号）
            assert result["intent_type"] in ["blood_pressure", "appointment", "unclear"], \
                f"包含表情符号的消息应该能够识别意图，实际为 {result['intent_type']}"
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_confidence_validation():
    """
    测试用例 7: identify_intent（置信度验证）
    
    验证：
    - 置信度范围正确（0.0-1.0）
    - 高置信度对应明确的意图
    - 低置信度对应不明确的意图
    - need_clarification 与置信度一致
    """
    test_name = "identify_intent（置信度验证）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试明确的意图（应该高置信度）
        print("\n--- 测试明确的意图 ---")
        clear_intent_cases = [
            ("我想记录血压，收缩压120，舒张压80", "blood_pressure"),
            ("我想预约内科", "appointment"),
        ]
        
        for message_text, expected_intent in clear_intent_cases:
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            print(f"\n消息: {message_text}")
            print(f"  预期意图: {expected_intent}")
            print(f"  实际意图: {result['intent_type']}")
            print(f"  置信度: {result['confidence']}")
            
            # 验证意图类型
            assert result["intent_type"] == expected_intent, \
                f"意图类型应该为 {expected_intent}，实际为 {result['intent_type']}"
            
            # 验证置信度应该较高
            assert result["confidence"] >= 0.7, \
                f"明确意图的置信度应该 >= 0.7，实际为 {result['confidence']}"
            
            # 如果置信度 >= 0.8，应该不需要澄清
            if result["confidence"] >= 0.8:
                assert result["need_clarification"] == False, \
                    f"高置信度({result['confidence']})时应该不需要澄清"
        
        # 测试不明确的意图（应该低置信度）
        print("\n--- 测试不明确的意图 ---")
        unclear_intent_cases = [
            "你好",
            "在吗",
            "有什么功能",
        ]
        
        for message_text in unclear_intent_cases:
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            print(f"\n消息: {message_text}")
            print(f"  意图类型: {result['intent_type']}")
            print(f"  置信度: {result['confidence']}")
            
            # 验证意图类型
            assert result["intent_type"] == "unclear", \
                f"不明确的意图应该识别为unclear，实际为 {result['intent_type']}"
            
            # 验证置信度应该较低
            assert result["confidence"] < 0.8, \
                f"不明确意图的置信度应该 < 0.8，实际为 {result['confidence']}"
            
            # 验证需要澄清
            assert result["need_clarification"] == True, \
                "不明确的意图应该需要澄清"
        
        # 验证所有结果的置信度范围
        print("\n--- 验证置信度范围 ---")
        all_cases = [
            "我想记录血压",
            "我想预约",
            "你好",
        ]
        
        for message_text in all_cases:
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            assert 0.0 <= result["confidence"] <= 1.0, \
                f"置信度应该在 0.0-1.0 之间，实际为 {result['confidence']}"
        
        print(f"  ✅ 所有置信度都在有效范围内")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def test_identify_intent_entities_extraction():
    """
    测试用例 8: identify_intent（实体提取）
    
    验证：
    - entities 字段存在
    - entities 是字典类型
    - 能够提取基本实体信息（如果实现）
    """
    test_name = "identify_intent（实体提取）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        test_cases = [
            "我想记录血压，收缩压120，舒张压80",
            "我想预约内科",
            "你好",
        ]
        
        for message_text in test_cases:
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            print(f"\n消息: {message_text}")
            print(f"  意图类型: {result['intent_type']}")
            
            # 验证 entities 字段存在
            assert "entities" in result, "结果应该包含 entities 字段"
            
            # 验证 entities 是字典类型
            assert isinstance(result["entities"], dict), \
                f"entities 应该是字典类型，实际为 {type(result['entities'])}"
            
            print(f"  ✅ entities 字段存在且类型正确: {result['entities']}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


def main():
    """运行所有测试"""
    print("="*60)
    print("路由工具测试 - identify_intent 函数（LLM 版本）")
    print("="*60)
    print("\n注意：此测试需要 LLM API 可用，可能需要一些时间...")
    
    # 运行所有测试用例
    test_identify_intent_blood_pressure_basic()
    # test_identify_intent_appointment_basic()
    # test_identify_intent_unclear_basic()
    # test_identify_intent_with_conversation_history()
    # test_identify_intent_complex_scenarios()
    # test_identify_intent_edge_cases()
    # test_identify_intent_confidence_validation()
    # test_identify_intent_entities_extraction()
    
    # 打印测试总结
    success = test_result.summary()
    
    # 返回退出码
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
