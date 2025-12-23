"""
测试 LangChain _convert_dict_to_message 函数对 reasoning_content 的处理

本测试验证：
1. LangChain 的 _convert_dict_to_message 函数确实会丢弃 reasoning_content 字段
2. Monkey Patch 方案可以有效保留 reasoning_content 字段
3. additional_kwargs 机制可以正常工作

注意：本测试不依赖项目的基础代码，直接测试 LangChain 的行为
"""
import os
import sys
import logging
from typing import Mapping, Any, Dict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_env_config() -> Dict[str, str]:
    """从 .env 文件加载配置（复制自其他测试文件）"""
    config = {}
    env_file = ".env"
    if not os.path.exists(env_file):
        env_file = ".env example"
    
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    return config


def test_original_behavior():
    """
    测试1：验证原始 _convert_dict_to_message 函数的行为
    
    预期结果：
    - reasoning_content 字段会被丢弃
    - additional_kwargs 中不包含 reasoning_content
    """
    logger.info("=" * 80)
    logger.info("测试1：验证原始 _convert_dict_to_message 函数的行为")
    logger.info("=" * 80)
    
    try:
        from langchain_openai.chat_models.base import _convert_dict_to_message
        from langchain_core.messages import AIMessage
        
        # 模拟火山引擎 API 返回的消息字典
        test_message_dict = {
            "role": "assistant",
            "content": "好的！已为您记录血压数据，收缩压120，舒张压80。",
            "reasoning_content": "嗯，用户让我帮忙记录血压数据，收缩压120，舒张压80。这组数字看起来是标准的理想血压值，符合正常范围。我需要确认用户是否还有其他信息需要记录。",
            "name": None,
            "id": None
        }
        
        # 调用原始函数
        message = _convert_dict_to_message(test_message_dict)
        
        # 验证结果
        logger.info(f"消息类型: {type(message)}")
        logger.info(f"消息内容: {message.content}")
        logger.info(f"additional_kwargs 键: {list(message.additional_kwargs.keys()) if hasattr(message, 'additional_kwargs') else 'N/A'}")
        
        # 检查 reasoning_content 是否存在
        if hasattr(message, 'additional_kwargs'):
            reasoning_content = message.additional_kwargs.get('reasoning_content')
            if reasoning_content:
                logger.error("❌ 测试失败：原始函数保留了 reasoning_content（这不应该发生）")
                logger.error(f"   reasoning_content: {reasoning_content[:100]}...")
                return False
            else:
                logger.info("✅ 测试通过：原始函数确实丢弃了 reasoning_content")
                logger.info(f"   additional_kwargs 内容: {message.additional_kwargs}")
                return True
        else:
            logger.error("❌ 测试失败：消息对象没有 additional_kwargs 属性")
            return False
            
    except Exception as e:
        logger.error(f"❌ 测试失败：发生异常 - {e}", exc_info=True)
        return False


def test_monkey_patch_solution():
    """
    测试2：验证 Monkey Patch 方案的有效性
    
    预期结果：
    - Monkey Patch 后，reasoning_content 会被保留
    - additional_kwargs 中包含 reasoning_content
    """
    logger.info("\n" + "=" * 80)
    logger.info("测试2：验证 Monkey Patch 方案的有效性")
    logger.info("=" * 80)
    
    try:
        from langchain_openai.chat_models.base import _convert_dict_to_message as _original_convert
        import langchain_openai.chat_models.base
        from langchain_core.messages import AIMessage
        
        # 保存原始函数
        original_function = _original_convert
        
        # 定义增强版函数
        def _enhanced_convert_dict_to_message(_dict: Mapping[str, Any]) -> AIMessage:
            """
            增强版的消息转换函数，保留 reasoning_content
            
            原理：在调用原始函数后，检查原始字典中是否有 reasoning_content，
            如果有，则将其添加到 additional_kwargs 中
            """
            # 调用原始函数
            message = original_function(_dict)
            
            # 如果是 AIMessage 且原始字典包含 reasoning_content
            if isinstance(message, AIMessage) and 'reasoning_content' in _dict:
                reasoning_content = _dict.get('reasoning_content')
                if reasoning_content:
                    # 确保 additional_kwargs 存在
                    if not hasattr(message, 'additional_kwargs') or message.additional_kwargs is None:
                        message.additional_kwargs = {}
                    # 添加 reasoning_content
                    message.additional_kwargs['reasoning_content'] = reasoning_content
                    logger.debug(f"已提取 reasoning_content，长度: {len(reasoning_content)}")
            
            return message
        
        # 应用 Monkey Patch
        logger.info("应用 Monkey Patch...")
        langchain_openai.chat_models.base._convert_dict_to_message = _enhanced_convert_dict_to_message
        
        # 模拟火山引擎 API 返回的消息字典
        test_message_dict = {
            "role": "assistant",
            "content": "好的！已为您记录血压数据，收缩压120，舒张压80。",
            "reasoning_content": "嗯，用户让我帮忙记录血压数据，收缩压120，舒张压80。这组数字看起来是标准的理想血压值，符合正常范围。我需要确认用户是否还有其他信息需要记录。",
            "name": None,
            "id": None
        }
        
        # 调用增强后的函数（通过模块引用）
        from langchain_openai.chat_models.base import _convert_dict_to_message
        message = _convert_dict_to_message(test_message_dict)
        
        # 验证结果
        logger.info(f"消息类型: {type(message)}")
        logger.info(f"消息内容: {message.content}")
        logger.info(f"additional_kwargs 键: {list(message.additional_kwargs.keys()) if hasattr(message, 'additional_kwargs') else 'N/A'}")
        
        # 检查 reasoning_content 是否存在
        if hasattr(message, 'additional_kwargs'):
            reasoning_content = message.additional_kwargs.get('reasoning_content')
            if reasoning_content:
                logger.info("✅ 测试通过：Monkey Patch 成功保留了 reasoning_content")
                logger.info(f"   reasoning_content 长度: {len(reasoning_content)} 字符")
                logger.info(f"   reasoning_content 预览: {reasoning_content[:200]}...")
                logger.info(f"   additional_kwargs 完整内容: {message.additional_kwargs}")
                return True
            else:
                logger.error("❌ 测试失败：Monkey Patch 后仍然没有 reasoning_content")
                logger.error(f"   additional_kwargs 内容: {message.additional_kwargs}")
                return False
        else:
            logger.error("❌ 测试失败：消息对象没有 additional_kwargs 属性")
            return False
            
    except Exception as e:
        logger.error(f"❌ 测试失败：发生异常 - {e}", exc_info=True)
        return False
    finally:
        # 恢复原始函数（可选，用于清理）
        try:
            langchain_openai.chat_models.base._convert_dict_to_message = original_function
            logger.info("已恢复原始函数")
        except:
            pass


def test_additional_kwargs_mechanism():
    """
    测试3：验证 additional_kwargs 机制本身是否正常工作
    
    预期结果：
    - AIMessage 对象支持 additional_kwargs
    - 可以手动设置和读取 additional_kwargs
    """
    logger.info("\n" + "=" * 80)
    logger.info("测试3：验证 additional_kwargs 机制本身是否正常工作")
    logger.info("=" * 80)
    
    try:
        from langchain_core.messages import AIMessage
        
        # 创建 AIMessage 对象
        message = AIMessage(
            content="测试内容",
            additional_kwargs={"test_field": "test_value", "reasoning_content": "测试思考过程"}
        )
        
        # 验证 additional_kwargs
        if hasattr(message, 'additional_kwargs'):
            logger.info(f"✅ AIMessage 支持 additional_kwargs")
            logger.info(f"   additional_kwargs 类型: {type(message.additional_kwargs)}")
            logger.info(f"   additional_kwargs 内容: {message.additional_kwargs}")
            
            # 验证可以读取 reasoning_content
            reasoning_content = message.additional_kwargs.get('reasoning_content')
            if reasoning_content:
                logger.info(f"✅ 可以成功读取 reasoning_content: {reasoning_content}")
                return True
            else:
                logger.error("❌ 无法读取 reasoning_content")
                return False
        else:
            logger.error("❌ AIMessage 没有 additional_kwargs 属性")
            return False
            
    except Exception as e:
        logger.error(f"❌ 测试失败：发生异常 - {e}", exc_info=True)
        return False


def test_field_preservation_comparison():
    """
    测试4：对比哪些字段被保留，哪些字段被丢弃
    
    预期结果：
    - function_call, tool_calls, audio 等字段会被保留
    - reasoning_content 字段会被丢弃（除非使用 Monkey Patch）
    """
    logger.info("\n" + "=" * 80)
    logger.info("测试4：对比字段保留情况")
    logger.info("=" * 80)
    
    try:
        from langchain_openai.chat_models.base import _convert_dict_to_message
        
        # 创建一个包含多种字段的消息字典
        test_message_dict = {
            "role": "assistant",
            "content": "测试内容",
            "function_call": {"name": "test_function", "arguments": "{}"},
            "tool_calls": [],
            "audio": None,
            "reasoning_content": "这是思考过程",
            "custom_field": "自定义字段",
            "name": None,
            "id": None
        }
        
        message = _convert_dict_to_message(test_message_dict)
        
        logger.info("字段保留情况：")
        logger.info(f"  content: {'✅' if message.content else '❌'}")
        
        if hasattr(message, 'additional_kwargs'):
            additional_kwargs = message.additional_kwargs or {}
            logger.info(f"  function_call: {'✅' if 'function_call' in additional_kwargs else '❌'}")
            logger.info(f"  tool_calls: {'✅' if 'tool_calls' in additional_kwargs else '❌'}")
            logger.info(f"  audio: {'✅' if 'audio' in additional_kwargs else '❌'}")
            logger.info(f"  reasoning_content: {'✅' if 'reasoning_content' in additional_kwargs else '❌'}")
            logger.info(f"  custom_field: {'✅' if 'custom_field' in additional_kwargs else '❌'}")
            
            logger.info(f"\n完整的 additional_kwargs: {additional_kwargs}")
            
            # 总结
            preserved_fields = [k for k in ['function_call', 'tool_calls', 'audio'] if k in additional_kwargs]
            discarded_fields = [k for k in ['reasoning_content', 'custom_field'] if k not in additional_kwargs]
            
            logger.info(f"\n✅ 被保留的字段: {preserved_fields}")
            logger.info(f"❌ 被丢弃的字段: {discarded_fields}")
            
            return True
        else:
            logger.error("❌ 消息对象没有 additional_kwargs 属性")
            return False
            
    except Exception as e:
        logger.error(f"❌ 测试失败：发生异常 - {e}", exc_info=True)
        return False


def main():
    """
    主测试函数
    """
    logger.info("=" * 80)
    logger.info("LangChain reasoning_content 提取可行性测试")
    logger.info("=" * 80)
    logger.info("")
    logger.info("测试目标：")
    logger.info("1. 验证 _convert_dict_to_message 函数确实会丢弃 reasoning_content")
    logger.info("2. 验证 Monkey Patch 方案可以有效保留 reasoning_content")
    logger.info("3. 验证 additional_kwargs 机制本身是否正常工作")
    logger.info("4. 对比哪些字段被保留，哪些字段被丢弃")
    logger.info("")
    
    results = []
    
    # 执行测试
    results.append(("测试1：原始行为", test_original_behavior()))
    results.append(("测试2：Monkey Patch 方案", test_monkey_patch_solution()))
    results.append(("测试3：additional_kwargs 机制", test_additional_kwargs_mechanism()))
    results.append(("测试4：字段保留对比", test_field_preservation_comparison()))
    
    # 输出总结
    logger.info("\n" + "=" * 80)
    logger.info("测试总结")
    logger.info("=" * 80)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    logger.info("")
    logger.info(f"总计: {len(results)} 个测试")
    logger.info(f"通过: {passed} 个")
    logger.info(f"失败: {failed} 个")
    
    if failed == 0:
        logger.info("\n🎉 所有测试通过！")
        return 0
    else:
        logger.error(f"\n⚠️  有 {failed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

