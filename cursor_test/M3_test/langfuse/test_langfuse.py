from langgraph.graph import StateGraph, END
from langfuse import Langfuse
from langfuse.decorators import langfuse_context, observe
from langchain_core.runnables import RunnableConfig

# 初始化 Langfuse（可选，自动从 env 读取）
langfuse = Langfuse()

# 示例状态
class GraphState(TypedDict):
    messages: list

def node_a(state: GraphState) -> GraphState:
    # 你的节点逻辑
    return {"messages": state["messages"] + ["Hello from A"]}

def node_b(state: GraphState) -> GraphState:
    return {"messages": state["messages"] + ["Hello from B"]}

# 构建图
workflow = StateOfGraph(GraphState)
workflow.add_node("a", node_a)
workflow.add_node("b", node_b)
workflow.set_entry_point("a")
workflow.add_edge("a", "b")
workflow.add_edge("b", END)

app = workflow.compile()

# 调用时传入 Langfuse 回调
from langfuse.langchain import LangfuseCallbackHandler

callback = LangfuseCallbackHandler()

config = RunnableConfig(callbacks=[callback])

result = app.invoke({"messages": ["Start"]}, config=config)