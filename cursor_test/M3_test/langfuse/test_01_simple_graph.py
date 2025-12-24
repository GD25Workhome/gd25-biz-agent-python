"""
测试 1：最简单的 LangGraph 调用（无 LLM）

目的：
- 验证 Langfuse 环境配置正确
- 验证基本的 Trace 和 Span 追踪
- 验证在 Dashboard 中能看到执行流程
"""
import os
import sys
from typing import TypedDict, List
from pathlib import Path
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langfuse import Langfuse
from langchain_core.runnables import RunnableConfig

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, project_root)

# 加载 .env 文件
env_path = Path(project_root) / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # 尝试加载 .env example
    env_example_path = Path(project_root) / ".env example"
    if env_example_path.exists():
        load_dotenv(env_example_path)


# 定义图状态
class SimpleGraphState(TypedDict):
    """简单的图状态，只包含消息列表"""
    messages: List[str]
    step_count: int


# 全局变量，用于存储 Langfuse 客户端（在测试中设置）
_langfuse_client = None


def node_a(state: SimpleGraphState) -> SimpleGraphState:
    """
    节点 A：添加消息 "Hello from A"
    """
    # 手动创建 span 追踪节点执行
    if _langfuse_client:
        span = _langfuse_client.start_span(name="node_a", input=state)
    
    messages = state.get("messages", [])
    step_count = state.get("step_count", 0)
    result = {
        "messages": messages + ["Hello from A"],
        "step_count": step_count + 1
    }
    
    if _langfuse_client:
        span.update(output=result)
        span.end()
    
    return result


def node_b(state: SimpleGraphState) -> SimpleGraphState:
    """
    节点 B：添加消息 "Hello from B"
    """
    if _langfuse_client:
        span = _langfuse_client.start_span(name="node_b", input=state)
    
    messages = state.get("messages", [])
    step_count = state.get("step_count", 0)
    result = {
        "messages": messages + ["Hello from B"],
        "step_count": step_count + 1
    }
    
    if _langfuse_client:
        span.update(output=result)
        span.end()
    
    return result


def node_c(state: SimpleGraphState) -> SimpleGraphState:
    """
    节点 C：添加消息 "Hello from C" 并完成
    """
    if _langfuse_client:
        span = _langfuse_client.start_span(name="node_c", input=state)
    
    messages = state.get("messages", [])
    step_count = state.get("step_count", 0)
    result = {
        "messages": messages + ["Hello from C - Done!"],
        "step_count": step_count + 1
    }
    
    if _langfuse_client:
        span.update(output=result)
        span.end()
    
    return result


def create_simple_graph():
    """
    创建简单的 LangGraph，包含 3 个节点：A -> B -> C -> END
    """
    # 创建状态图
    workflow = StateGraph(SimpleGraphState)
    
    # 添加节点
    workflow.add_node("node_a", node_a)
    workflow.add_node("node_b", node_b)
    workflow.add_node("node_c", node_c)
    
    # 设置入口点
    workflow.set_entry_point("node_a")
    
    # 添加边：A -> B -> C -> END
    workflow.add_edge("node_a", "node_b")
    workflow.add_edge("node_b", "node_c")
    workflow.add_edge("node_c", END)
    
    # 编译图
    return workflow.compile()


def test_simple_graph_with_langfuse():
    """
    测试简单的 LangGraph 调用，使用 Langfuse 追踪
    """
    print("=" * 60)
    print("测试 1：最简单的 LangGraph 调用（无 LLM）")
    print("=" * 60)
    
    # 初始化 Langfuse（从环境变量读取配置）
    from app.core.config import settings
    langfuse_public_key = settings.LANGFUSE_PUBLIC_KEY
    langfuse_secret_key = settings.LANGFUSE_SECRET_KEY
    langfuse_host = settings.LANGFUSE_HOST
    
    if not langfuse_public_key or not langfuse_secret_key or not langfuse_host:
        print("❌ 错误：未找到 Langfuse 凭据")
        print("   请确保 .env 文件中配置了：")
        print("   - LANGFUSE_PUBLIC_KEY")
        print("   - LANGFUSE_SECRET_KEY")
        print("   - LANGFUSE_HOST")
        return False
    
    print(f"✅ Langfuse 配置检查通过")
    print(f"   - Public Key: {langfuse_public_key[:20]}...")
    print(f"   - Host: {langfuse_host}")
    
    # 初始化 Langfuse 客户端
    global _langfuse_client
    _langfuse_client = Langfuse(
        public_key=langfuse_public_key,
        secret_key=langfuse_secret_key,
        host=langfuse_host
    )
    
    # 创建 Trace（用于在 Dashboard 中识别）
    # 注意：Langfuse 3.x 使用 start_span 创建 trace
    trace = _langfuse_client.start_span(
        name="test_01_simple_graph",
        metadata={
            "test_name": "测试1：最简单的LangGraph调用",
            "description": "验证基本的Trace和Span追踪，不涉及LLM调用",
            "nodes": ["node_a", "node_b", "node_c"]
        }
    )
    
    print(f"✅ 创建 Trace: {trace.id}")
    
    # 创建图
    graph = create_simple_graph()
    print("✅ 创建 LangGraph")
    
    # 准备初始状态
    initial_state: SimpleGraphState = {
        "messages": ["Start"],
        "step_count": 0
    }
    
    print(f"📥 初始状态: {initial_state}")
    
    # 在 trace 上下文中执行图
    # 节点函数会手动创建 span
    trace.update(input=initial_state)
    print("\n🚀 开始执行图...")
    result = graph.invoke(initial_state)
    trace.update(output=result)
    
    print(f"✅ 执行完成")
    print(f"📤 最终状态: {result}")
    
    # 结束 trace
    trace.end()
    
    # 确保数据被发送到 Langfuse
    _langfuse_client.flush()
    print(f"✅ 数据已刷新到 Langfuse")
    
    # 验证结果
    assert "messages" in result, "结果中应包含 messages"
    assert "step_count" in result, "结果中应包含 step_count"
    assert len(result["messages"]) == 4, f"应该有4条消息，实际有{len(result['messages'])}条"
    assert result["step_count"] == 3, f"应该执行了3步，实际执行了{result['step_count']}步"
    
    print("\n" + "=" * 60)
    print("✅ 测试通过！")
    print("=" * 60)
    print(f"\n📊 请在 Langfuse Dashboard 中查看结果：")
    print(f"   {langfuse_host}")
    print(f"   Trace ID: {trace.trace_id}")
    print(f"\n预期看到：")
    print(f"   - 1 个 Trace（test_01_simple_graph）")
    print(f"   - 3 个 Span（node_a, node_b, node_c）")
    print(f"   - 每个 Span 显示输入/输出状态")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        success = test_simple_graph_with_langfuse()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

