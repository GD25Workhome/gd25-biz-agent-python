"""
最小化流程测试
测试动态流程与Langfuse日志记录的核心功能

测试场景：
1. 设置Trace上下文
2. 创建双节点连续流程
3. 执行流程（两个节点依次执行）
4. 验证Langfuse日志记录

运行方式：
从项目根目录运行：
    python -m cursor_test.langfuse.02flow.test_minimal_flow
或：
    cd cursor_test/langfuse/02flow && python test_minimal_flow.py
"""
import sys
from pathlib import Path

# 将当前目录添加到 Python 路径（支持从项目根目录或测试目录运行）
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

import secrets
import logging
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

# 导入抽取的代码
from core.state import FlowState
from core.definition import FlowDefinition, NodeDefinition, EdgeDefinition
from flows.builder import GraphBuilder
from langfuse_local.handler import set_langfuse_trace_context
from llm.providers.manager import ProviderManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_minimal_flow_definition() -> FlowDefinition:
    """
    创建最小化流程定义
    
    双节点连续流程，包含两个连续的Agent节点
    """
    return FlowDefinition(
        name="test_minimal_flow",
        version="1.0.0",
        description="最小化流程测试 - 连续两个节点",
        nodes=[
            NodeDefinition(
                name="agent_node_1",
                type="agent",
                config={
                    "prompt": "你是一个友好的AI助手。请简洁地回答用户的问题，并在回答后提示用户将继续处理。",  # 简化版：直接是字符串
                    "model": {
                        "provider": "doubao",  # 从环境变量读取
                        "name": "doubao-seed-1-6-251015",
                        "temperature": 0.7
                    },
                    "tools": []  # 简化版：不使用工具
                }
            ),
            NodeDefinition(
                name="agent_node_2",
                type="agent",
                config={
                    "prompt": "你是一个专业的AI助手。请基于前一轮对话的内容，提供更详细的补充说明或建议。",  # 简化版：直接是字符串
                    "model": {
                        "provider": "doubao",  # 从环境变量读取
                        "name": "doubao-seed-1-6-251015",
                        "temperature": 0.7
                    },
                    "tools": []  # 简化版：不使用工具
                }
            )
        ],
        edges=[
            EdgeDefinition(
                from_node="agent_node_1",
                to_node="agent_node_2",
                condition="always"  # 无条件连接，第一个节点执行完后自动进入第二个节点
            )
        ],
        entry_node="agent_node_1"
    )


def test_minimal_flow():
    """
    测试最小化流程
    
    核心测试流程：
    1. 设置Trace上下文（关键！）
    2. 创建流程定义
    3. 构建图
    4. 编译图
    5. 执行流程
    6. 验证结果
    """
    logger.info("=" * 80)
    logger.info("开始测试最小化流程")
    logger.info("=" * 80)
    
    # 0. 加载模型供应商配置（从YAML文件读取）
    logger.info("[步骤0] 加载模型供应商配置...")
    try:
        ProviderManager.load_providers()
        logger.info("[步骤0] 模型供应商配置加载成功")
    except Exception as e:
        logger.error(f"[步骤0] 模型供应商配置加载失败: {e}", exc_info=True)
        raise
    
    # 1. 设置Trace上下文（关键！必须在执行流程之前）
    trace_id = secrets.token_hex(16)  # 生成32位十六进制字符
    logger.info(f"[步骤1] 生成Trace ID: {trace_id}")
    
    langfuse_trace_id = set_langfuse_trace_context(
        name="test_minimal_flow",
        user_id="test_user",
        session_id="test_session",
        trace_id=trace_id,
        metadata={
            "test": True,
            "flow_name": "test_minimal_flow"
        }
    )
    
    if langfuse_trace_id:
        logger.info(f"[步骤1] 设置Trace上下文成功: trace_id={langfuse_trace_id}")
    else:
        logger.warning("[步骤1] 设置Trace上下文失败或Langfuse未启用")
    
    # 2. 创建流程定义
    logger.info("[步骤2] 创建流程定义...")
    flow_def = create_minimal_flow_definition()
    logger.info(f"[步骤2] 流程定义创建成功: {flow_def.name}, 节点数: {len(flow_def.nodes)}, 边数: {len(flow_def.edges)}")
    logger.info(f"[步骤2] 入口节点: {flow_def.entry_node}")
    for i, node in enumerate(flow_def.nodes, 1):
        logger.info(f"[步骤2]   节点{i}: {node.name} (类型: {node.type})")
    for i, edge in enumerate(flow_def.edges, 1):
        logger.info(f"[步骤2]   边{i}: {edge.from_node} -> {edge.to_node} (条件: {edge.condition})")
    
    # 3. 构建图
    logger.info("[步骤3] 构建图...")
    graph = GraphBuilder.build_graph(flow_def)
    logger.info("[步骤3] 图构建成功")
    
    # 4. 编译图
    logger.info("[步骤4] 编译图...")
    checkpoint = MemorySaver()
    compiled_graph = graph.compile(checkpointer=checkpoint)
    logger.info("[步骤4] 图编译成功")
    
    # 5. 构建初始状态
    logger.info("[步骤5] 构建初始状态...")
    initial_state: FlowState = {
        "messages": [HumanMessage(content="你好，请介绍一下你自己")],
        "session_id": "test_session",
    }
    logger.info(f"[步骤5] 初始状态构建成功: messages_count={len(initial_state['messages'])}")
    
    # 6. 执行流程
    logger.info("[步骤6] 执行流程...")
    logger.info("-" * 80)
    try:
        config = {"configurable": {"thread_id": "test_session"}}
        result = compiled_graph.invoke(initial_state, config)
        
        logger.info("-" * 80)
        logger.info("[步骤6] 流程执行成功")
        
        # 7. 验证结果
        logger.info("[步骤7] 验证结果...")
        messages = result.get("messages", [])
        logger.info(f"[步骤7] 结果消息数: {len(messages)}")
        
        if messages:
            # 显示所有AI消息（两个节点应该各产生一条）
            ai_messages = [msg for msg in messages if hasattr(msg, "type") and msg.type == "ai"]
            logger.info(f"[步骤7] AI消息数: {len(ai_messages)}")
            
            for i, msg in enumerate(ai_messages, 1):
                response_text = msg.content if hasattr(msg, "content") else str(msg)
                logger.info(f"[步骤7] 节点{i}响应: {response_text[:150]}...")
            
            if ai_messages:
                last_message = ai_messages[-1]
                response_text = last_message.content if hasattr(last_message, "content") else str(last_message)
                logger.info(f"[步骤7] 最终响应: {response_text[:200]}...")
        
        logger.info("=" * 80)
        logger.info("测试完成")
        logger.info(f"Trace ID: {langfuse_trace_id or trace_id}")
        logger.info("=" * 80)
        
        # TODO: 验证Langfuse日志记录
        # 可以通过Langfuse API或UI验证Trace是否正确记录
        logger.info("提示: 请在Langfuse UI中查看Trace记录")
        
    except Exception as e:
        logger.error(f"[步骤6] 流程执行失败: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        test_minimal_flow()
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        raise

