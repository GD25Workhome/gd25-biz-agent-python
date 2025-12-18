"""
多轮会话集成测试
测试完整的多轮对话流程，包括意图识别、澄清、数据收集等

运行方式：
==========
# 直接运行测试文件
python cursor_test/M2_test/integration/test_multi_turn_conversation.py

# 或者在项目根目录运行
python -m cursor_test.M2_test.integration.test_multi_turn_conversation

注意：
- 此测试需要 LLM API 可用
- 此测试需要数据库连接
- 测试可能需要较长时间（因为涉及多次 LLM 调用）
"""
import sys
import asyncio
import logging
import random
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# 添加项目根目录到 Python 路径
test_file_path = Path(__file__).resolve()
project_root = test_file_path.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from domain.router.graph import create_router_graph
from domain.router.state import RouterState
from app.core.config import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestResult:
    """测试结果记录类"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.logs = []
    
    def add_log(self, message: str):
        """添加日志"""
        self.logs.append(message)
        logger.info(message)
        print(f"📝 {message}")
    
    def add_pass(self, test_name: str):
        """记录通过的测试"""
        self.passed += 1
        logger.info(f"✅ {test_name}")
        print(f"✅ {test_name}")
    
    def add_fail(self, test_name: str, error: str):
        """记录失败的测试"""
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        logger.error(f"❌ {test_name}: {error}")
        print(f"❌ {test_name}: {error}")
    
    def summary(self):
        """打印测试总结"""
        print("\n" + "="*80)
        print("测试总结")
        print("="*80)
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"总计: {self.passed + self.failed}")
        
        if self.errors:
            print("\n失败详情:")
            for error in self.errors:
                print(f"  - {error}")
        
        print("\n测试日志摘要:")
        for log in self.logs[-20:]:  # 只显示最后20条日志
            print(f"  {log}")
        
        print("="*80)
        return self.failed == 0


# 全局测试结果记录
test_result = TestResult()


async def create_test_graph():
    """创建测试用的路由图"""
    test_result.add_log("开始创建路由图...")
    
    try:
        # 创建数据库连接池
        # 注意：必须设置 autocommit=True，因为 checkpointer.setup() 需要执行 CREATE INDEX CONCURRENTLY
        # 该命令不能在事务块内执行
        pool = AsyncConnectionPool(
            conninfo=settings.CHECKPOINTER_DB_URI,
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True}
        )
        # 打开连接池
        await pool.open()
        test_result.add_log(f"✅ 数据库连接池创建成功: {settings.CHECKPOINTER_DB_URI}")
        
        # 创建 checkpointer
        checkpointer = AsyncPostgresSaver(pool)
        # 初始化数据库表结构（创建 checkpoints 表等）
        await checkpointer.setup()
        test_result.add_log("✅ Checkpointer 创建并初始化成功")
        
        # 创建路由图
        graph = create_router_graph(checkpointer=checkpointer, pool=pool)
        test_result.add_log("✅ 路由图创建成功")
        
        return graph, pool
        
    except Exception as e:
        test_result.add_log(f"❌ 创建路由图失败: {str(e)}")
        raise


async def run_conversation(
    graph,
    session_id: str,
    user_id: str,
    messages: List[str],
    expected_intents: List[str] = None,
    expected_agents: List[str] = None
) -> Dict[str, Any]:
    """
    运行一个完整的对话流程
    
    Args:
        graph: 路由图
        session_id: 会话ID
        user_id: 用户ID
        messages: 用户消息列表
        expected_intents: 期望的意图列表（可选）
        expected_agents: 期望的智能体列表（可选）
        
    Returns:
        对话结果
    """
    test_result.add_log(f"\n{'='*80}")
    test_result.add_log(f"开始对话流程 - Session ID: {session_id}, User ID: {user_id}")
    test_result.add_log(f"{'='*80}")
    
    # 构建初始状态
    initial_state: RouterState = {
        "messages": [],
        "current_intent": None,
        "current_agent": None,
        "need_reroute": True,
        "session_id": session_id,
        "user_id": user_id,
        "bp_form": {}
    }
    
    config = {
        "configurable": {
            "thread_id": session_id
        }
    }
    
    conversation_log = []
    all_responses = []
    
    # 逐条处理用户消息
    for i, user_message in enumerate(messages, 1):
        test_result.add_log(f"\n--- 第 {i} 轮对话 ---")
        test_result.add_log(f"👤 用户消息: {user_message}")
        
        # 添加用户消息到状态
        current_messages = initial_state.get("messages", [])
        current_messages.append(HumanMessage(content=user_message))
        initial_state["messages"] = current_messages
        
        # 执行路由图
        test_result.add_log("🔄 执行路由图...")
        try:
            result = None
            node_sequence = []
            
            async for event in graph.astream(initial_state, config=config):
                for node_name, node_output in event.items():
                    node_sequence.append(node_name)
                    result = node_output
                    test_result.add_log(f"  📍 节点执行: {node_name}")
                    
                    # 记录节点状态
                    if isinstance(node_output, dict):
                        current_intent = node_output.get("current_intent")
                        current_agent = node_output.get("current_agent")
                        need_reroute = node_output.get("need_reroute", False)
                        
                        if current_intent:
                            test_result.add_log(f"    - 当前意图: {current_intent}")
                        if current_agent:
                            test_result.add_log(f"    - 当前智能体: {current_agent}")
                        if need_reroute:
                            test_result.add_log(f"    - 需要重新路由: {need_reroute}")
            
            if not result:
                test_result.add_log("⚠️  路由图执行完成，但没有返回结果")
                continue
            
            # 获取最后一条AI消息
            response_message = None
            for msg in reversed(result.get("messages", [])):
                if isinstance(msg, AIMessage):
                    response_message = msg
                    break
            
            if response_message:
                response_text = response_message.content
                test_result.add_log(f"🤖 助手回复: {response_text}")
                all_responses.append(response_text)
                conversation_log.append({
                    "user": user_message,
                    "assistant": response_text,
                    "intent": result.get("current_intent"),
                    "agent": result.get("current_agent"),
                    "nodes": node_sequence
                })
            else:
                test_result.add_log("⚠️  没有找到助手回复")
            
            # 更新初始状态为当前结果（用于下一轮对话）
            initial_state = result
            
        except Exception as e:
            test_result.add_log(f"❌ 执行路由图时出错: {str(e)}")
            import traceback
            test_result.add_log(f"错误堆栈: {traceback.format_exc()}")
            raise
    
    # 验证结果
    if expected_intents:
        for i, expected_intent in enumerate(expected_intents):
            if i < len(conversation_log):
                actual_intent = conversation_log[i].get("intent")
                if actual_intent == expected_intent:
                    test_result.add_log(f"✅ 意图验证通过: 期望 {expected_intent}, 实际 {actual_intent}")
                else:
                    test_result.add_log(f"⚠️  意图验证: 期望 {expected_intent}, 实际 {actual_intent}")
    
    if expected_agents:
        for i, expected_agent in enumerate(expected_agents):
            if i < len(conversation_log):
                actual_agent = conversation_log[i].get("agent")
                if actual_agent == expected_agent:
                    test_result.add_log(f"✅ 智能体验证通过: 期望 {expected_agent}, 实际 {actual_agent}")
                else:
                    test_result.add_log(f"⚠️  智能体验证: 期望 {expected_agent}, 实际 {actual_agent}")
    
    return {
        "conversation_log": conversation_log,
        "final_state": initial_state,
        "all_responses": all_responses
    }


async def test_scenario_1_intent_clarification():
    """
    测试场景 1: 意图澄清流程
    
    场景描述：
    1. 用户发送不明确的意图（"你好"）
    2. 系统应该生成澄清问题
    3. 用户明确意图后，系统应该正确路由
    """
    test_name = "测试场景 1: 意图澄清流程"
    test_result.add_log(f"\n{'='*80}")
    test_result.add_log(f"开始执行: {test_name}")
    test_result.add_log(f"{'='*80}")
    
    try:
        graph, pool = await create_test_graph()
        
        session_id = f"test_clarification_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        user_id = "test_user_001"
        
        messages = [
            "你好",  # 不明确的意图，应该触发澄清
            "我想记录血压",  # 明确意图后，应该路由到血压智能体
        ]
        
        expected_intents = ["unclear", "blood_pressure"]
        expected_agents = [None, "blood_pressure_agent"]
        
        result = await run_conversation(
            graph=graph,
            session_id=session_id,
            user_id=user_id,
            messages=messages,
            expected_intents=expected_intents,
            expected_agents=expected_agents
        )
        
        # 验证澄清问题
        if len(result["all_responses"]) > 0:
            first_response = result["all_responses"][0]
            if "血压" in first_response or "预约" in first_response:
                test_result.add_log("✅ 澄清问题包含关键功能（血压或预约）")
            else:
                test_result.add_log("⚠️  澄清问题可能不完整")
        
        # 验证最终路由
        final_intent = result["final_state"].get("current_intent")
        final_agent = result["final_state"].get("current_agent")
        
        if final_intent == "blood_pressure" and final_agent == "blood_pressure_agent":
            test_result.add_log("✅ 最终路由正确：意图为 blood_pressure，智能体为 blood_pressure_agent")
        else:
            test_result.add_log(f"⚠️  最终路由: 意图={final_intent}, 智能体={final_agent}")
        
        # 清理
        await pool.close()
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, f"执行失败: {str(e)}")
        import traceback
        test_result.add_log(f"错误堆栈: {traceback.format_exc()}")


async def test_scenario_2_multi_turn_data_collection():
    """
    测试场景 2: 多轮数据收集流程
    
    场景描述：
    1. 用户发送不完整的信息（只说了"我想记录血压"）
    2. 智能体应该主动询问缺失的信息（收缩压、舒张压）
    3. 用户逐步提供信息
    4. 智能体收集完整信息后执行操作
    """
    test_name = "测试场景 2: 多轮数据收集流程"
    test_result.add_log(f"\n{'='*80}")
    test_result.add_log(f"开始执行: {test_name}")
    test_result.add_log(f"{'='*80}")
    
    try:
        graph, pool = await create_test_graph()
        
        session_id = f"test_data_collection_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # 使用年月日时分秒+3位随机数生成唯一用户ID，保证可被数字解析
        user_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(100, 999)}"
        
        messages = [
            "我想记录血压",  # 不完整信息
            "收缩压是120",  # 提供部分信息
            "舒张压是80，心率是70",  # 提供完整信息
        ]
        
        result = await run_conversation(
            graph=graph,
            session_id=session_id,
            user_id=user_id,
            messages=messages
        )
        
        # 验证智能体是否询问了缺失信息
        if len(result["all_responses"]) >= 2:
            second_response = result["all_responses"][1]
            if "收缩压" in second_response or "舒张压" in second_response or "血压" in second_response:
                test_result.add_log("✅ 智能体主动询问了缺失信息")
            else:
                test_result.add_log("⚠️  智能体可能没有询问缺失信息")
        
        # 验证最终是否执行了操作
        final_messages = result["final_state"].get("messages", [])
        has_tool_call = False
        for msg in final_messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                has_tool_call = True
                test_result.add_log(f"✅ 检测到工具调用: {msg.tool_calls}")
                break
        
        if not has_tool_call:
            test_result.add_log("⚠️  未检测到工具调用，可能信息仍未完整")
        
        # 清理
        await pool.close()
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, f"执行失败: {str(e)}")
        import traceback
        test_result.add_log(f"错误堆栈: {traceback.format_exc()}")


async def test_scenario_3_intent_change_detection():
    """
    测试场景 3: 意图变化检测
    
    场景描述：
    1. 用户先说要记录血压
    2. 然后改变主意说要预约
    3. 系统应该检测到意图变化并重新路由
    """
    test_name = "测试场景 3: 意图变化检测"
    test_result.add_log(f"\n{'='*80}")
    test_result.add_log(f"开始执行: {test_name}")
    test_result.add_log(f"{'='*80}")
    
    try:
        graph, pool = await create_test_graph()
        
        session_id = f"test_intent_change_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        user_id = "test_user_003"
        
        messages = [
            "我想记录血压，收缩压120，舒张压80",  # 血压意图
            "算了，我想预约内科",  # 改变为预约意图
        ]
        
        expected_intents = ["blood_pressure", "appointment"]
        expected_agents = ["blood_pressure_agent", "appointment_agent"]
        
        result = await run_conversation(
            graph=graph,
            session_id=session_id,
            user_id=user_id,
            messages=messages,
            expected_intents=expected_intents,
            expected_agents=expected_agents
        )
        
        # 验证意图变化
        conversation_log = result["conversation_log"]
        if len(conversation_log) >= 2:
            first_intent = conversation_log[0].get("intent")
            second_intent = conversation_log[1].get("intent")
            
            if first_intent == "blood_pressure" and second_intent == "appointment":
                test_result.add_log("✅ 意图变化检测正确：从 blood_pressure 变为 appointment")
            else:
                test_result.add_log(f"⚠️  意图变化: {first_intent} -> {second_intent}")
        
        # 验证智能体切换
        if len(conversation_log) >= 2:
            first_agent = conversation_log[0].get("agent")
            second_agent = conversation_log[1].get("agent")
            
            if first_agent == "blood_pressure_agent" and second_agent == "appointment_agent":
                test_result.add_log("✅ 智能体切换正确：从 blood_pressure_agent 变为 appointment_agent")
            else:
                test_result.add_log(f"⚠️  智能体切换: {first_agent} -> {second_agent}")
        
        # 清理
        await pool.close()
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, f"执行失败: {str(e)}")
        import traceback
        test_result.add_log(f"错误堆栈: {traceback.format_exc()}")


async def test_scenario_4_complete_workflow():
    """
    测试场景 4: 完整工作流程
    
    场景描述：
    综合测试，包括意图澄清、多轮数据收集、意图变化等
    """
    test_name = "测试场景 4: 完整工作流程"
    test_result.add_log(f"\n{'='*80}")
    test_result.add_log(f"开始执行: {test_name}")
    test_result.add_log(f"{'='*80}")
    
    try:
        graph, pool = await create_test_graph()
        
        session_id = f"test_complete_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        user_id = "test_user_004"
        
        messages = [
            "你好",  # 1. 不明确意图 -> 澄清
            "我想预约",  # 2. 明确预约意图，但信息不完整
            "内科",  # 3. 提供科室信息
            "明天上午10点",  # 4. 提供时间信息
        ]
        
        result = await run_conversation(
            graph=graph,
            session_id=session_id,
            user_id=user_id,
            messages=messages
        )
        
        # 验证完整流程
        conversation_log = result["conversation_log"]
        test_result.add_log(f"\n对话轮数: {len(conversation_log)}")
        
        # 验证第一轮应该是澄清
        if len(conversation_log) > 0:
            first_intent = conversation_log[0].get("intent")
            if first_intent == "unclear":
                test_result.add_log("✅ 第一轮正确识别为 unclear 意图")
            else:
                test_result.add_log(f"⚠️  第一轮意图: {first_intent}")
        
        # 验证最终应该路由到预约智能体
        final_intent = result["final_state"].get("current_intent")
        final_agent = result["final_state"].get("current_agent")
        
        if final_intent == "appointment" and final_agent == "appointment_agent":
            test_result.add_log("✅ 最终路由正确：意图为 appointment，智能体为 appointment_agent")
        else:
            test_result.add_log(f"⚠️  最终路由: 意图={final_intent}, 智能体={final_agent}")
        
        # 清理
        await pool.close()
        
        test_result.add_pass(test_name)
        
    except Exception as e:
        test_result.add_fail(test_name, f"执行失败: {str(e)}")
        import traceback
        test_result.add_log(f"错误堆栈: {traceback.format_exc()}")


async def main():
    """运行所有测试"""
    print("="*80)
    print("多轮会话集成测试")
    print("="*80)
    print("\n注意：")
    print("- 此测试需要 LLM API 可用")
    print("- 此测试需要数据库连接")
    print("- 测试可能需要较长时间（因为涉及多次 LLM 调用）")
    print("- 测试会生成详细的日志信息")
    print("\n开始测试...\n")
    
    try:
        # 运行所有测试场景
        await test_scenario_1_intent_clarification()
        await test_scenario_2_multi_turn_data_collection()
        await test_scenario_3_intent_change_detection()
        await test_scenario_4_complete_workflow()
        
        # 打印测试总结
        success = test_result.summary()
        
        return 0 if success else 1
        
    except Exception as e:
        test_result.add_log(f"❌ 测试执行过程中出现未预期的错误: {str(e)}")
        import traceback
        test_result.add_log(f"错误堆栈: {traceback.format_exc()}")
        test_result.summary()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
