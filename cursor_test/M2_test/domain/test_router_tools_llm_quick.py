"""
路由工具测试 - LLM 版本意图识别（快速验证版）
快速验证核心功能是否正常工作
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
test_file_path = Path(__file__).resolve()
project_root = test_file_path.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain_core.messages import HumanMessage, AIMessage
from domain.router.tools.router_tools import identify_intent


def test_basic_intents():
    """测试基本意图识别"""
    print("="*60)
    print("快速验证测试 - LLM 意图识别")
    print("="*60)
    
    test_cases = [
        ("我想记录血压，收缩压120，舒张压80", "blood_pressure"),
        ("我想预约内科", "appointment"),
        ("你好", "unclear"),
    ]
    
    passed = 0
    failed = 0
    
    for message_text, expected_intent in test_cases:
        try:
            messages = [HumanMessage(content=message_text)]
            result = identify_intent.invoke({"messages": messages})
            
            intent_type = result.get("intent_type")
            confidence = result.get("confidence", 0.0)
            
            if intent_type == expected_intent:
                print(f"✅ {message_text[:30]:30} -> {intent_type} (置信度: {confidence:.2f})")
                passed += 1
            else:
                print(f"❌ {message_text[:30]:30} -> 期望: {expected_intent}, 实际: {intent_type}")
                failed += 1
        except Exception as e:
            print(f"❌ {message_text[:30]:30} -> 错误: {str(e)}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"测试结果: 通过 {passed}, 失败 {failed}, 总计 {passed + failed}")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = test_basic_intents()
    exit(0 if success else 1)
