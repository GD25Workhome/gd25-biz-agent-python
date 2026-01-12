# Langfuse RunnableCallable Span 产生原因分析

## 问题描述

在执行 `workflow.add_node("supervisor", supervisor_chain)` 时，Langfuse 会记录一个名为 `RunnableCallable` 的 span。本文档分析产生这个 span 的原因。

## 原因分析

### 1. Supervisor Chain 的构建方式

在代码中，`supervisor_chain` 的构建方式如下：

```493:497:cursor_test/langfuse/04multiAgent/test_Ex2_multiAgentLangGraph.py
    supervisor_chain = (
        prompt
        | structured_llm
        | parse_route_decision
    )
```

这个链由三个部分组成：
1. **`prompt`** - `ChatPromptTemplate`，LangChain 的提示词模板（实现了 `Runnable` 接口）
2. **`structured_llm`** - `llm.with_structured_output(RouteDecision)`，带结构化输出的 LLM（实现了 `Runnable` 接口）
3. **`parse_route_decision`** - 普通的 Python 函数，用于将 Pydantic 模型转换为字典

### 2. LangChain Runnable 接口机制

在 LangChain 中，所有可执行的组件都实现了 `Runnable` 接口：

- **RunnableSequence**：由多个 Runnable 通过 `|` 操作符连接而成的链
- **RunnableLambda**：将普通 Python 函数包装成 Runnable
- **RunnableCallable**：Langfuse 对某些 Runnable 类型的识别名称

当您使用 `prompt | structured_llm | parse_route_decision` 时：
1. `prompt` 和 `structured_llm` 本身就是 Runnable
2. `parse_route_decision` 是一个普通 Python 函数
3. LangChain 会自动将 `parse_route_decision` 包装成 `RunnableLambda` 或类似的 Runnable 类型

### 3. LangGraph 节点的执行机制

当您将 `supervisor_chain` 添加到 LangGraph 节点时：

```python
workflow.add_node("supervisor", supervisor_chain)
```

LangGraph 会：
1. 将 `supervisor_chain` 包装成一个可调用的节点函数
2. 在执行节点时，调用这个链的 `invoke()` 方法
3. 链会依次执行：`prompt` → `structured_llm` → `parse_route_decision`

### 4. Langfuse 的追踪机制

Langfuse 的 `CallbackHandler` 会：
1. 监听所有实现了 `Runnable` 接口的组件的执行
2. 为每个 Runnable 创建相应的 span
3. 根据 Runnable 的类型和名称来标识 span

**关键点**：
- Langfuse 会为整个链（`supervisor_chain`）创建一个 span
- 同时也会为链中的每个组件创建子 span
- 对于包含普通 Python 函数的链，Langfuse 可能会将其识别为 `RunnableCallable`

### 5. RunnableCallable 名称的来源

`RunnableCallable` 这个名称可能来自于：

1. **LangChain 内部类型**：
   - 当普通 Python 函数被包装成 Runnable 时，LangChain 会创建一个 `RunnableLambda` 或 `RunnableCallable` 类型的对象
   - Langfuse 在追踪时，会读取这个对象的类型信息

2. **Langfuse 的识别逻辑**：
   - Langfuse 会根据 Runnable 对象的 `__class__.__name__` 或类似属性来命名 span
   - 如果无法识别具体的类型，可能会使用默认名称 `RunnableCallable`

3. **链的整体识别**：
   - 当整个链被添加到 LangGraph 节点时，LangGraph 可能会将其包装成一个特殊的可调用对象
   - Langfuse 在追踪时，可能会将这个包装后的对象识别为 `RunnableCallable`

## 解决方案

### 方案一：为链设置 run_name（推荐）

您可以在链上设置 `run_name`，这样 Langfuse 会使用这个名称而不是默认的 `RunnableCallable`：

```python
def create_supervisor_chain(llm: ChatOpenAI):
    # ... 现有代码 ...
    
    supervisor_chain = (
        prompt
        | structured_llm
        | parse_route_decision
    )
    
    # 为链设置名称
    supervisor_chain = supervisor_chain.with_config({"run_name": "supervisor_chain"})
    
    return supervisor_chain
```

### 方案二：使用节点包装函数

将链包装在一个节点函数中，这样可以更好地控制 span 的名称：

```python
def supervisor_node(state):
    """
    监督者节点函数
    
    这个函数会被 Langfuse 识别为节点函数，而不是 RunnableCallable
    """
    result = supervisor_chain.invoke(state)
    return result

# 在构建图时使用节点函数
workflow.add_node("supervisor", supervisor_node)
```

### 方案三：使用 RunnableConfig

在执行图时，通过 `RunnableConfig` 设置 `run_name`：

```python
from langchain_core.runnables import RunnableConfig

config = {
    "callbacks": [langfuse_handler],
    "configurable": {
        "thread_id": session_id
    },
    "run_name": "supervisor"  # 设置节点名称
}

for s in graph.stream(
    {"messages": [HumanMessage(content=question)]},
    config=config
):
    print(s)
```

## 验证方法

要验证 span 的名称是否已更改，您可以：

1. **查看 Langfuse UI**：
   - 在 Langfuse 的追踪记录中，查看 span 的名称是否已更新

2. **添加日志**：
   ```python
   import logging
   logger = logging.getLogger(__name__)
   
   # 在执行链之前记录信息
   logger.info(f"Supervisor chain type: {type(supervisor_chain)}")
   logger.info(f"Supervisor chain name: {getattr(supervisor_chain, 'name', 'N/A')}")
   ```

## 总结

`RunnableCallable` span 的产生是因为：

1. **`supervisor_chain` 是一个 LangChain 链**，实现了 `Runnable` 接口
2. **链中包含普通 Python 函数**（`parse_route_decision`），被 LangChain 包装成 Runnable
3. **LangGraph 将链包装成节点**，Langfuse 在追踪时识别为 `RunnableCallable`
4. **这是正常的行为**，表示 Langfuse 正在追踪链的执行

如果您希望使用更友好的名称，可以使用上述方案之一来设置自定义的 `run_name`。

---

**文档版本**：V1.0  
**创建时间**：2025-01-XX  
**相关文件**：`cursor_test/langfuse/04multiAgent/test_Ex2_multiAgentLangGraph.py`

