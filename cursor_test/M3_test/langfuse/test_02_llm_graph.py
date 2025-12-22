"""
测试 2：带 LLM 调用的简单 LangGraph

目的：
- 验证 LLM 调用被正确追踪
- 验证 Generation 类型的 Span
- 验证 tokens 使用情况
"""
import os
import sys
from typing import TypedDict, List
from pathlib import Path
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langfuse import Langfuse
from langchain_core.messages import HumanMessage, AIMessage
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

# 导入项目的 LLM 客户端
from infrastructure.llm.client import get_llm


# 定义图状态
class LLMGraphState(TypedDict):
    """包含消息和 LLM 响应的图状态"""
    messages: List[str]
    llm_response: str
    step_count: int


# 全局变量，用于存储 Langfuse 客户端和 trace（在测试中设置）
_langfuse_client = None
_current_trace = None


def prepare_llm_node(state: LLMGraphState) -> LLMGraphState:
    """
    节点：准备 LLM 调用
    将消息转换为 LangChain 消息格式
    """
    if _langfuse_client:
        span = _langfuse_client.start_span(name="prepare_llm_node", input=state)
    
    messages = state.get("messages", [])
    # 将字符串消息转换为 LangChain 消息格式（用于后续 LLM 调用）
    langchain_messages = [HumanMessage(content=msg) for msg in messages]
    
    result = {
        **state,
        "langchain_messages": langchain_messages,
        "step_count": state.get("step_count", 0) + 1
    }
    
    if _langfuse_client:
        span.update(output={"prepared_messages_count": len(langchain_messages)})
        span.end()
    
    return result


def call_llm_node(state: LLMGraphState) -> LLMGraphState:
    """
    节点：调用 LLM
    使用项目的 get_llm() 函数调用 LLM
    使用 Langfuse 手动追踪 LLM 调用
    """
    if _langfuse_client and _current_trace:
        span = _langfuse_client.start_span(
            name="call_llm_node",
            input={"messages_count": len(state.get("langchain_messages", []))}
        )
    
    # 获取 LangChain 消息
    langchain_messages = state.get("langchain_messages", [])
    if not langchain_messages:
        # 如果没有消息，创建一个默认消息
        langchain_messages = [HumanMessage(content="你好，请简单介绍一下你自己。")]
    
    # 准备输入文本（用于 Langfuse Generation）
    input_text = "\n".join([msg.content if hasattr(msg, 'content') else str(msg) for msg in langchain_messages])
    
    # 创建 Generation span 来追踪 LLM 调用
    generation = None
    if _langfuse_client and _current_trace:
        generation = _current_trace.start_generation(
            name="llm_call",
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            input=input_text,
            metadata={
                "node": "call_llm_node",
                "messages_count": len(langchain_messages)
            }
        )
    
    # 获取 LLM 实例
    llm = get_llm(
        temperature=0.7,
        enable_logging=False  # 禁用项目的日志，使用 Langfuse 追踪
    )
    
    # 调用 LLM
    try:
        response = llm.invoke(langchain_messages)
        llm_response_text = response.content if hasattr(response, 'content') else str(response)
        
        # 更新 Generation span
        if generation:
            # 尝试获取 usage 信息（如果 LLM 返回了）
            usage = None
            if hasattr(response, 'response_metadata') and response.response_metadata:
                usage_info = response.response_metadata.get('token_usage', {})
                if usage_info:
                    usage = {
                        "prompt_tokens": usage_info.get("prompt_tokens", 0),
                        "completion_tokens": usage_info.get("completion_tokens", 0),
                        "total_tokens": usage_info.get("total_tokens", 0)
                    }
            
            generation.update(
                output=llm_response_text,
                usage=usage
            )
            generation.end()
            
    except Exception as e:
        llm_response_text = f"LLM 调用失败: {str(e)}"
        if generation:
            generation.update(
                output=llm_response_text,
                level="ERROR",
                status_message=str(e)
            )
            generation.end()
        if _langfuse_client and _current_trace:
            span.update(status_message=f"Error: {str(e)}", level="ERROR")
    
    result = {
        **state,
        "llm_response": llm_response_text,
        "step_count": state.get("step_count", 0) + 1
    }
    
    if _langfuse_client and _current_trace:
        span.update(output={"response_length": len(llm_response_text)})
        span.end()
    
    return result


def process_response_node(state: LLMGraphState) -> LLMGraphState:
    """
    节点：处理 LLM 响应
    将响应添加到消息列表中
    """
    if _langfuse_client:
        span = _langfuse_client.start_span(name="process_response_node", input=state)
    
    messages = state.get("messages", [])
    llm_response = state.get("llm_response", "")
    
    # 将 LLM 响应添加到消息列表
    messages.append(f"LLM回复: {llm_response}")
    
    result = {
        **state,
        "messages": messages,
        "step_count": state.get("step_count", 0) + 1
    }
    
    if _langfuse_client:
        span.update(output={"final_messages_count": len(messages)})
        span.end()
    
    return result


def create_llm_graph():
    """
    创建包含 LLM 调用的 LangGraph
    流程：prepare -> call_llm -> process -> END
    """
    # 创建状态图
    workflow = StateGraph(LLMGraphState)
    
    # 添加节点
    workflow.add_node("prepare_llm", prepare_llm_node)
    workflow.add_node("call_llm", call_llm_node)
    workflow.add_node("process_response", process_response_node)
    
    # 设置入口点
    workflow.set_entry_point("prepare_llm")
    
    # 添加边：prepare -> call_llm -> process -> END
    workflow.add_edge("prepare_llm", "call_llm")
    workflow.add_edge("call_llm", "process_response")
    workflow.add_edge("process_response", END)
    
    # 编译图
    return workflow.compile()


def test_llm_graph_with_langfuse():
    """
    测试包含 LLM 调用的 LangGraph，使用 Langfuse 追踪
    """
    print("=" * 60)
    print("测试 2：带 LLM 调用的简单 LangGraph")
    print("=" * 60)
    
    # 初始化 Langfuse（从环境变量读取配置）
    langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    langfuse_host = os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    
    if not langfuse_public_key or not langfuse_secret_key:
        print("❌ 错误：未找到 Langfuse 凭据")
        print("   请确保 .env 文件中配置了：")
        print("   - LANGFUSE_PUBLIC_KEY")
        print("   - LANGFUSE_SECRET_KEY")
        print("   - LANGFUSE_BASE_URL (可选)")
        return False
    
    # 检查 LLM 配置
    llm_api_key = os.getenv("OPENAI_API_KEY")
    if not llm_api_key:
        print("❌ 错误：未找到 LLM API Key")
        print("   请确保 .env 文件中配置了：")
        print("   - OPENAI_API_KEY")
        return False
    
    print(f"✅ Langfuse 配置检查通过")
    print(f"   - Public Key: {langfuse_public_key[:20]}...")
    print(f"   - Host: {langfuse_host}")
    print(f"✅ LLM 配置检查通过")
    print(f"   - API Key: {llm_api_key[:20]}...")
    
    # 初始化 Langfuse 客户端
    global _langfuse_client, _current_trace
    _langfuse_client = Langfuse(
        public_key=langfuse_public_key,
        secret_key=langfuse_secret_key,
        host=langfuse_host
    )
    
    # 创建 Trace（用于在 Dashboard 中识别）
    _current_trace = _langfuse_client.start_span(
        name="test_02_llm_graph",
        metadata={
            "test_name": "测试2：带LLM调用的LangGraph",
            "description": "验证LLM调用被正确追踪，包括Generation Span和tokens统计",
            "nodes": ["prepare_llm", "call_llm", "process_response"]
        }
    )
    
    print(f"✅ 创建 Trace: {_current_trace.id}")
    
    # 创建图
    graph = create_llm_graph()
    print("✅ 创建 LangGraph（包含 LLM 调用）")
    
    # 准备初始状态
    initial_state: LLMGraphState = {
        "messages": ["用户消息: 你好"],
        "llm_response": "",
        "step_count": 0
    }
    
    print(f"📥 初始状态: {initial_state}")
    
    # 在 trace 上下文中执行图
    _current_trace.update(input=initial_state)
    print("\n🚀 开始执行图（将调用 LLM）...")
    
    try:
        result = graph.invoke(initial_state)
        _current_trace.update(output=result)
        
        print(f"✅ 执行完成")
        print(f"📤 最终状态:")
        print(f"   - 消息数量: {len(result.get('messages', []))}")
        print(f"   - LLM 响应: {result.get('llm_response', '')[:100]}...")
        print(f"   - 执行步数: {result.get('step_count', 0)}")
        
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        _current_trace.update(status_message=f"Error: {str(e)}", level="ERROR")
        raise
    
    finally:
        # 结束 trace
        _current_trace.end()
        
        # 确保数据被发送到 Langfuse
        _langfuse_client.flush()
        print(f"✅ 数据已刷新到 Langfuse")
    
    # 验证结果
    assert "messages" in result, "结果中应包含 messages"
    assert "llm_response" in result, "结果中应包含 llm_response"
    assert result["llm_response"], "LLM 响应不应为空"
    assert result["step_count"] == 3, f"应该执行了3步，实际执行了{result['step_count']}步"
    
    print("\n" + "=" * 60)
    print("✅ 测试通过！")
    print("=" * 60)
    print(f"\n📊 请在 Langfuse Dashboard 中查看结果：")
    print(f"   {langfuse_host}")
    print(f"   Trace ID: {_current_trace.trace_id}")
    print(f"\n预期看到：")
    print(f"   - 1 个 Trace（test_02_llm_graph）")
    print(f"   - 3 个 Span（prepare_llm, call_llm, process_response）")
    print(f"   - call_llm 节点中应该有 Generation Span（LLM 调用）")
    print(f"   - Generation Span 应该显示：")
    print(f"     * 输入 prompt")
    print(f"     * 输出 response")
    print(f"     * Tokens 使用情况（如果 LLM 支持）")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        success = test_llm_graph_with_langfuse()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

