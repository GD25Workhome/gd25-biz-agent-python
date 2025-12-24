"""
Langfuse 集成示例
演示如何在 LangGraph 中使用 Langfuse 进行追踪
"""
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langfuse import Langfuse
from langchain_core.runnables import RunnableConfig

# 初始化 Langfuse（可选，自动从 env 读取）
try:
    langfuse = Langfuse()
except Exception as e:
    print(f"Langfuse初始化失败: {e}")
    langfuse = None

# 示例状态
class GraphState(TypedDict):
    messages: list

def node_a(state: GraphState) -> GraphState:
    """节点A：添加消息"""
    return {"messages": state["messages"] + ["Hello from A"]}

def node_b(state: GraphState) -> GraphState:
    """节点B：添加消息"""
    return {"messages": state["messages"] + ["Hello from B"]}

# 构建图
workflow = StateGraph(GraphState)
workflow.add_node("a", node_a)
workflow.add_node("b", node_b)
workflow.set_entry_point("a")
workflow.add_edge("a", "b")
workflow.add_edge("b", END)

app = workflow.compile()

# 调用时传入 Langfuse 回调（如果可用）
try:
    from langfuse.langchain import LangfuseCallbackHandler
    callback = LangfuseCallbackHandler()
    config = RunnableConfig(callbacks=[callback])
except ImportError:
    print("Langfuse LangChain 回调不可用，使用默认配置")
    config = RunnableConfig()

# 执行图
if __name__ == "__main__":
    result = app.invoke({"messages": ["Start"]}, config=config)
    print(f"结果: {result}")