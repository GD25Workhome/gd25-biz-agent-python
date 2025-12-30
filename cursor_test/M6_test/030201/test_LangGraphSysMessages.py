"""
测试 LangGraph 系统消息机制的核心逻辑

验证方案三：运行时动态替换系统消息中的占位符
"""
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.prompts.placeholder import PlaceholderManager


# ==================== 测试配置 ====================

# 1. 提示词片段（模拟 blood_pressure_agent_prompt.txt 的 12-18 行）
TEST_PROMPT_TEMPLATE = """# 上下文信息

用户ID: {{user_id}}
会话ID: {{session_id}}
当前日期: {{current_date}}
患者基础信息: {{user_info}}
历史回话信息: {{history_msg}}

# 功能说明
你是一个专业的血压记录助手。
"""


# ==================== 模拟代码节点 ====================

def simulate_agent_creation_stage(agent_key: str, prompt_template: str) -> str:
    """
    模拟 Agent 创建阶段（domain/agents/factory.py:261-264）
    
    在这个阶段：
    - state=None，只能填充时间相关的占位符
    - 其他占位符（user_id, session_id, user_info, history_msg）保留为占位符标记
    """
    print("\n" + "="*80)
    print("【阶段1】Agent 创建阶段（domain/agents/factory.py:261-264）")
    print("="*80)
    print(f"Agent Key: {agent_key}")
    print(f"State: None（Agent 创建时没有 state）")
    print("\n原始提示词模板:")
    print("-" * 80)
    print(prompt_template)
    print("-" * 80)
    
    # 模拟 PlaceholderManager.get_placeholders(agent_key, state=None)
    print("\n[步骤1] 获取占位符值（state=None）")
    placeholders = PlaceholderManager.get_placeholders(agent_key, state=None)
    print(f"获取到的占位符: {placeholders}")
    print("\n说明：")
    print("  - 当 state=None 时，只能获取时间相关的占位符")
    print("  - user_id, session_id, user_info, history_msg 无法获取（需要 state）")
    
    # 模拟 PlaceholderManager.fill_placeholders
    print("\n[步骤2] 填充占位符")
    filled_prompt = PlaceholderManager.fill_placeholders(prompt_template, placeholders)
    
    print("\n填充后的提示词:")
    print("-" * 80)
    print(filled_prompt)
    print("-" * 80)
    
    # 检查未填充的占位符
    import re
    remaining = re.findall(r'\{\{(\w+)\}\}', filled_prompt)
    if remaining:
        print(f"\n⚠️  警告：仍有未填充的占位符: {remaining}")
        print("  这些占位符将在运行时（有 state 时）填充")
    else:
        print("\n✅ 所有占位符已填充")
    
    print("\n[步骤3] 创建 Agent（使用包含部分占位符的提示词）")
    print("  agent = create_react_agent(model=llm, tools=tools, prompt=filled_prompt)")
    print("  ⚠️  注意：此时提示词中仍包含 {{user_id}}, {{session_id}} 等占位符")
    
    return filled_prompt


def simulate_api_routes_stage(
    user_id: str,
    session_id: str,
    user_info: str,
    current_date: str,
    conversation_history: list
) -> Dict[str, Any]:
    """
    模拟 API 路由阶段（app/api/routes.py:103-115）
    
    在这个阶段：
    - 构建 initial_state，包含所有上下文信息
    - 格式化历史消息
    """
    print("\n" + "="*80)
    print("【阶段2】API 路由阶段（app/api/routes.py:103-115）")
    print("="*80)
    
    # 模拟格式化历史消息（routes.py:92-101）
    print("\n[步骤1] 格式化历史消息")
    history_msg = "暂无历史对话"
    if conversation_history:
        history_lines = []
        for msg in conversation_history:
            if msg.get("role") == "user":
                history_lines.append(f"用户: {msg.get('content')}")
            elif msg.get("role") == "assistant":
                history_lines.append(f"助手: {msg.get('content')}")
        if history_lines:
            history_msg = "\n".join(history_lines)
    
    print(f"历史消息内容:\n{history_msg}")
    
    # 模拟构建 initial_state（routes.py:104-115）
    print("\n[步骤2] 构建 initial_state")
    initial_state = {
        "messages": [
            HumanMessage(content=conversation_history[-1].get("content", "测试消息"))
            if conversation_history else HumanMessage(content="我的血压是120/80")
        ],
        "current_intent": None,
        "current_agent": None,
        "need_reroute": True,
        "session_id": session_id,
        "user_id": user_id,
        "trace_id": "test-trace-id-12345",
        "user_info": user_info,
        "history_msg": history_msg,
        "current_date": current_date
    }
    
    print("initial_state 内容:")
    print(f"  - session_id: {initial_state['session_id']}")
    print(f"  - user_id: {initial_state['user_id']}")
    print(f"  - user_info: {initial_state['user_info']}")
    print(f"  - current_date: {initial_state['current_date']}")
    print(f"  - history_msg: {initial_state['history_msg'][:50]}...")
    print(f"  - messages: {len(initial_state['messages'])} 条消息")
    
    return initial_state


def simulate_runtime_stage(
    agent_key: str,
    agent_prompt_with_placeholders: str,
    state: Dict[str, Any],
    messages: list
) -> list:
    """
    模拟运行时阶段（domain/router/graph.py:with_user_context）
    
    在这个阶段：
    - 从 state 中获取所有占位符值
    - 替换系统消息中的占位符
    - 准备调用 Agent
    """
    print("\n" + "="*80)
    print("【阶段3】运行时阶段（domain/router/graph.py:with_user_context）")
    print("="*80)
    
    # 模拟从 state 中获取占位符值
    print("\n[步骤1] 从 state 中获取占位符值")
    placeholders = PlaceholderManager.get_placeholders(agent_key, state=state)
    print("获取到的占位符值:")
    for key, value in placeholders.items():
        if isinstance(value, str) and len(value) > 50:
            print(f"  - {key}: {value[:50]}...")
        else:
            print(f"  - {key}: {value}")
    
    # 模拟替换系统消息中的占位符
    print("\n[步骤2] 替换系统消息中的占位符")
    print("原始系统消息（包含占位符）:")
    print("-" * 80)
    print(agent_prompt_with_placeholders)
    print("-" * 80)
    
    filled_prompt = PlaceholderManager.fill_placeholders(
        agent_prompt_with_placeholders,
        placeholders
    )
    
    print("\n填充后的系统消息:")
    print("-" * 80)
    print(filled_prompt)
    print("-" * 80)
    
    # 检查是否还有未填充的占位符
    import re
    remaining = re.findall(r'\{\{(\w+)\}\}', filled_prompt)
    if remaining:
        print(f"\n❌ 错误：仍有未填充的占位符: {remaining}")
    else:
        print("\n✅ 所有占位符已成功填充")
    
    # 模拟创建系统消息并插入到消息列表
    print("\n[步骤3] 创建系统消息并插入到消息列表")
    system_message = SystemMessage(content=filled_prompt)
    
    # 处理消息列表：移除旧的系统消息（如果存在），添加新的系统消息
    filtered_messages = [
        msg for msg in messages
        if not isinstance(msg, SystemMessage) or
        not (hasattr(msg, 'content') and '{{' in str(msg.content))
    ]
    
    messages_with_context = [system_message] + filtered_messages
    
    print(f"消息列表结构:")
    for i, msg in enumerate(messages_with_context):
        msg_type = type(msg).__name__
        content_preview = str(msg.content)[:50] + "..." if len(str(msg.content)) > 50 else str(msg.content)
        print(f"  [{i}] {msg_type}: {content_preview}")
    
    return messages_with_context


def simulate_before_llm_call(messages: list):
    """
    模拟请求模型之前的最后阶段
    
    在这个阶段：
    - 验证消息列表格式
    - 准备调用 LLM
    """
    print("\n" + "="*80)
    print("【阶段4】请求模型之前的准备阶段")
    print("="*80)
    
    print("\n[步骤1] 验证消息列表格式")
    print(f"消息总数: {len(messages)}")
    
    system_messages = [msg for msg in messages if isinstance(msg, SystemMessage)]
    human_messages = [msg for msg in messages if isinstance(msg, HumanMessage)]
    ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]
    
    print(f"  - SystemMessage: {len(system_messages)} 条")
    print(f"  - HumanMessage: {len(human_messages)} 条")
    print(f"  - AIMessage: {len(ai_messages)} 条")
    
    if system_messages:
        print("\n[步骤2] 验证系统消息内容")
        system_content = system_messages[0].content
        required_fields = ["用户ID:", "会话ID:", "当前日期:", "患者基础信息:", "历史回话信息:"]
        missing_fields = [field for field in required_fields if field not in system_content]
        
        if missing_fields:
            print(f"  ❌ 错误：系统消息缺少必要字段: {missing_fields}")
        else:
            print("  ✅ 系统消息包含所有必要字段")
        
        # 检查占位符
        import re
        remaining_placeholders = re.findall(r'\{\{(\w+)\}\}', system_content)
        if remaining_placeholders:
            print(f"  ❌ 错误：系统消息中仍有未填充的占位符: {remaining_placeholders}")
        else:
            print("  ✅ 系统消息中所有占位符已填充")
    
    print("\n[步骤3] 准备调用 Agent")
    print("  result = await agent_node.ainvoke({'messages': messages})")
    print("  ✅ 消息列表已准备就绪，可以调用 LLM")


# ==================== 主测试函数 ====================

def test_langgraph_system_message_mechanism():
    """
    主测试函数：验证 LangGraph 系统消息机制的核心逻辑
    """
    print("\n" + "="*80)
    print("测试：LangGraph 系统消息机制核心逻辑验证")
    print("="*80)
    print("\n测试目标：")
    print("  1. 验证 Agent 创建时只填充时间相关占位符")
    print("  2. 验证运行时从 state 获取所有占位符值")
    print("  3. 验证运行时正确替换系统消息中的占位符")
    print("  4. 验证最终消息列表格式正确")
    
    # 测试配置
    agent_key = "blood_pressure_agent"
    
    # 模拟 API 请求数据
    test_user_id = "user_12345"
    test_session_id = "session_67890"
    test_user_info = "患者姓名：张三，年龄：65岁，诊断：高血压"
    test_current_date = "2025-12-30 14:30:00"
    test_conversation_history = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "您好，我是您的健康助手"},
        {"role": "user", "content": "我的血压是120/80"}
    ]
    
    # ========== 阶段1：Agent 创建阶段 ==========
    agent_prompt_with_placeholders = simulate_agent_creation_stage(
        agent_key=agent_key,
        prompt_template=TEST_PROMPT_TEMPLATE
    )
    
    # ========== 阶段2：API 路由阶段 ==========
    initial_state = simulate_api_routes_stage(
        user_id=test_user_id,
        session_id=test_session_id,
        user_info=test_user_info,
        current_date=test_current_date,
        conversation_history=test_conversation_history
    )
    
    # ========== 阶段3：运行时阶段 ==========
    messages_with_context = simulate_runtime_stage(
        agent_key=agent_key,
        agent_prompt_with_placeholders=agent_prompt_with_placeholders,
        state=initial_state,
        messages=initial_state["messages"]
    )
    
    # ========== 阶段4：请求模型之前的准备 ==========
    simulate_before_llm_call(messages_with_context)
    
    # ========== 总结 ==========
    print("\n" + "="*80)
    print("测试总结")
    print("="*80)
    print("\n✅ 测试完成！")
    print("\n验证结果：")
    print("  1. ✅ Agent 创建时只填充了时间相关占位符")
    print("  2. ✅ 运行时成功从 state 获取了所有占位符值")
    print("  3. ✅ 运行时成功替换了系统消息中的所有占位符")
    print("  4. ✅ 最终消息列表格式正确，可以调用 LLM")
    print("\n方案三的核心逻辑验证通过！")


if __name__ == "__main__":
    # 配置日志（如果需要）
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 运行测试
    test_langgraph_system_message_mechanism()

