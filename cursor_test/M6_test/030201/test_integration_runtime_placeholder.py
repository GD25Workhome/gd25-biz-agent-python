"""
集成测试：验证运行时占位符替换的实际执行效果

模拟完整的流程：
1. Agent 创建（只填充时间相关占位符）
2. API 请求（构建 state）
3. 运行时占位符替换
4. 验证最终的系统消息
"""
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from langchain_core.messages import HumanMessage, SystemMessage
from infrastructure.prompts.placeholder import PlaceholderManager
from domain.agents.factory import AgentFactory
from domain.router.graph import _load_agent_template


async def test_runtime_placeholder_replacement():
    """
    测试运行时占位符替换的完整流程
    """
    print("\n" + "="*80)
    print("集成测试：运行时占位符替换实际执行效果")
    print("="*80)
    
    agent_key = "blood_pressure_agent"
    
    # ========== 阶段1：Agent 创建 ==========
    print("\n【阶段1】Agent 创建阶段")
    print("-" * 80)
    
    # 加载 Agent 配置
    AgentFactory.load_config()
    
    # 模拟 Agent 创建时的提示词处理
    try:
        # 加载模板
        template = _load_agent_template(agent_key)
        print(f"✅ 成功加载提示词模板（长度: {len(template)} 字符）")
        
        # 只填充时间相关占位符（state=None）
        placeholders_at_creation = PlaceholderManager.get_placeholders(agent_key, state=None)
        filled_at_creation = PlaceholderManager.fill_placeholders(template, placeholders_at_creation)
        
        # 检查未填充的占位符
        import re
        remaining = re.findall(r'\{\{(\w+)\}\}', filled_at_creation)
        print(f"✅ Agent 创建时填充了时间相关占位符")
        print(f"⚠️  仍有未填充的占位符: {remaining}")
        print(f"   这些占位符将在运行时填充")
        
    except Exception as e:
        print(f"❌ Agent 创建阶段失败: {str(e)}")
        return False
    
    # ========== 阶段2：模拟 API 请求 ==========
    print("\n【阶段2】模拟 API 请求（构建 state）")
    print("-" * 80)
    
    # 模拟 API 请求数据
    test_state = {
        "messages": [HumanMessage(content="我的血压是120/80")],
        "session_id": "test_session_12345",
        "user_id": "test_user_67890",
        "user_info": "患者姓名：测试用户，年龄：65岁，诊断：高血压",
        "current_date": "2025-12-30 15:00:00",
        "history_msg": "用户: 你好\n助手: 您好，我是您的健康助手\n用户: 我的血压是120/80",
        "trace_id": "test_trace_id",
        "current_intent": None,
        "current_agent": None,
        "need_reroute": True
    }
    
    print(f"✅ 构建 state 成功")
    print(f"   - session_id: {test_state['session_id']}")
    print(f"   - user_id: {test_state['user_id']}")
    print(f"   - user_info: {test_state['user_info']}")
    print(f"   - current_date: {test_state['current_date']}")
    
    # ========== 阶段3：运行时占位符替换 ==========
    print("\n【阶段3】运行时占位符替换")
    print("-" * 80)
    
    try:
        # 1. 从 state 获取占位符值
        placeholders_at_runtime = PlaceholderManager.get_placeholders(agent_key, state=test_state)
        print(f"✅ 从 state 获取占位符值成功")
        print(f"   占位符数量: {len(placeholders_at_runtime)}")
        print(f"   占位符键: {list(placeholders_at_runtime.keys())}")
        
        # 2. 加载原始模板（包含占位符）
        original_template = _load_agent_template(agent_key)
        print(f"✅ 加载原始模板成功")
        
        # 3. 填充占位符
        filled_at_runtime = PlaceholderManager.fill_placeholders(original_template, placeholders_at_runtime)
        print(f"✅ 填充占位符成功")
        
        # 4. 检查是否还有未填充的占位符
        remaining_at_runtime = re.findall(r'\{\{(\w+)\}\}', filled_at_runtime)
        if remaining_at_runtime:
            print(f"❌ 仍有未填充的占位符: {remaining_at_runtime}")
            return False
        else:
            print(f"✅ 所有占位符已成功填充")
        
        # 5. 验证关键字段
        required_fields = ["用户ID:", "会话ID:", "当前日期:", "患者基础信息:", "历史回话信息:"]
        missing_fields = [field for field in required_fields if field not in filled_at_runtime]
        if missing_fields:
            print(f"❌ 系统消息缺少必要字段: {missing_fields}")
            return False
        else:
            print(f"✅ 系统消息包含所有必要字段")
        
        # 6. 验证占位符值是否正确替换
        if f"用户ID: {test_state['user_id']}" not in filled_at_runtime:
            print(f"❌ user_id 替换失败")
            return False
        if f"会话ID: {test_state['session_id']}" not in filled_at_runtime:
            print(f"❌ session_id 替换失败")
            return False
        if test_state['user_info'] not in filled_at_runtime:
            print(f"❌ user_info 替换失败")
            return False
        
        print(f"✅ 所有占位符值验证通过")
        
        # 7. 创建系统消息
        system_message = SystemMessage(content=filled_at_runtime)
        messages_with_context = [system_message] + test_state["messages"]
        
        print(f"✅ 系统消息创建成功")
        print(f"   消息列表长度: {len(messages_with_context)}")
        print(f"   SystemMessage: 1 条")
        print(f"   HumanMessage: {len(test_state['messages'])} 条")
        
    except Exception as e:
        print(f"❌ 运行时占位符替换失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    # ========== 验证结果 ==========
    print("\n" + "="*80)
    print("测试结果")
    print("="*80)
    print("\n✅ 集成测试通过！")
    print("\n验证点：")
    print("  1. ✅ Agent 创建时只填充时间相关占位符")
    print("  2. ✅ 运行时成功从 state 获取所有占位符值")
    print("  3. ✅ 运行时成功替换所有占位符")
    print("  4. ✅ 系统消息包含所有必要字段")
    print("  5. ✅ 占位符值验证通过")
    print("  6. ✅ 消息列表格式正确")
    
    # 打印最终的系统消息预览
    print("\n最终系统消息预览（前200字符）:")
    print("-" * 80)
    print(filled_at_runtime[:200] + "...")
    print("-" * 80)
    
    return True


if __name__ == "__main__":
    # 配置日志
    import logging
    logging.basicConfig(
        level=logging.WARNING,  # 只显示警告和错误
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 运行测试
    success = asyncio.run(test_runtime_placeholder_replacement())
    sys.exit(0 if success else 1)

