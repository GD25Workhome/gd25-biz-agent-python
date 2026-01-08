# LangChain 对接 Langfuse 调用原理详解

## 文档来源

本文档基于以下官方文档和资料整理：
- [Langfuse 官方文档 - LangChain & LangGraph Integration](https://langfuse.com/integrations/frameworks/langchain)
- Langfuse 官方博客相关文章
- 项目实际代码实现分析

---

## 一、概述

### 1.1 什么是 LangChain

LangChain 是一个开源框架，帮助开发者构建由大语言模型（LLMs）驱动的应用程序，提供工具来连接模型与外部数据、API 和逻辑。

### 1.2 什么是 Langfuse

Langfuse 是一个用于 LLM 应用程序的可观测性和追踪平台。它捕获 LLM 交互过程中发生的一切：输入、输出、工具使用、重试、延迟和成本，允许您评估和调试应用程序。

### 1.3 集成方式

Langfuse 通过 **LangChain 的回调机制（Callback System）** 进行集成。Langfuse 提供了一个 `CallbackHandler`，可以作为回调传递给 LangChain 的链（Chain）或代理（Agent）。

---

## 二、核心调用原理

### 2.1 回调机制基础

LangChain 的回调系统允许在链执行的不同阶段插入自定义逻辑。Langfuse 利用这个机制来捕获执行过程中的详细信息。

**回调流程**：
```
LangChain 执行流程
    ↓
触发回调事件（on_chain_start, on_llm_start, on_tool_start 等）
    ↓
CallbackHandler 接收事件
    ↓
转换为 Langfuse 的 Trace/Span/Generation 结构
    ↓
发送到 Langfuse 平台
```

### 2.2 Langfuse CallbackHandler 工作原理

#### 2.2.1 基本结构

`CallbackHandler` 继承自 LangChain 的 `BaseCallbackHandler`，实现了以下关键回调方法：

- `on_chain_start/end`：链开始/结束时调用
- `on_llm_start/end`：LLM 调用开始/结束时调用
- `on_tool_start/end`：工具调用开始/结束时调用
- `on_retriever_start/end`：检索器开始/结束时调用

#### 2.2.2 数据映射关系

LangChain 的执行结构会被映射到 Langfuse 的层次结构：

```
Langfuse Trace（追踪）
  └─ Span（跨度）- 对应 LangChain Chain
      └─ Generation（生成）- 对应 LLM 调用
      └─ Span（跨度）- 对应 Tool 调用
      └─ Span（跨度）- 对应 Retriever 调用
```

#### 2.2.3 上下文管理（v3.x 版本）

Langfuse SDK v3.x 使用 `contextvars` 来管理追踪上下文：

1. **全局上下文**：通过 `contextvars.ContextVar` 存储当前活动的 Trace/Span
2. **自动关联**：`CallbackHandler` 会自动检测当前活动的 Trace，无需手动传递
3. **嵌套支持**：支持嵌套的 Span 结构，自动维护父子关系

---

## 三、版本差异与迁移

### 3.1 v3.x 版本（当前推荐）

#### 3.1.1 导入方式

```python
# v3.x 导入方式
from langfuse import Langfuse, get_client
from langfuse.langchain import CallbackHandler
```

#### 3.1.2 初始化方式

```python
# 1. 创建/配置 Langfuse 客户端（应用启动时执行一次）
Langfuse(
    public_key="pk-lf-...",
    secret_key="sk-lf-...",
    host="https://cloud.langfuse.com"
)

# 2. 获取单例实例并创建 Handler
langfuse = get_client()
handler = CallbackHandler()
```

**关键变化**：
- 使用单例模式，通过 `get_client()` 访问
- `CallbackHandler` 不再接受构造函数参数（如 `sample_rate`、`user_id` 等）
- 配置通过 Langfuse 客户端或环境变量提供

#### 3.1.3 使用方式

```python
from langchain.agents import create_agent
from langfuse.langchain import CallbackHandler

# 创建 Handler
handler = CallbackHandler()

# 在链调用时传递
agent.invoke(
    {"messages": [{"role": "user", "content": "what is 42 + 58?"}]},
    config={"callbacks": [handler]}
)
```

#### 3.1.4 动态属性设置

**方式一：通过 LangChain config metadata**

```python
chain.invoke(
    {"topic": "cats"},
    config={
        "callbacks": [handler],
        "metadata": {
            "langfuse_user_id": "user_123",
            "langfuse_session_id": "session_456"
        }
    }
)
```

**方式二：使用 Langfuse SDK 的 span 更新**

```python
from langfuse import get_client

langfuse = get_client()
with langfuse.start_as_current_span(name="my_operation") as span:
    span.update_trace(user_id="user_123", session_id="session_456")
    # 然后调用 LangChain
    chain.invoke({"input": "..."}, config={"callbacks": [handler]})
```

### 3.2 v2.x 版本（已废弃）

#### 3.2.1 导入方式

```python
# v2.x 导入方式
from langfuse.callback import CallbackHandler
```

#### 3.2.2 初始化方式

```python
# v2.x 可以接受构造函数参数
handler = CallbackHandler(
    public_key="pk-lf-...",
    secret_key="sk-lf-...",
    sample_rate=0.5,
    user_id="user_123"
)
```

#### 3.2.3 多调用行为变化

**v2.x 之前**：多次调用会合并到一个 Trace
```
TRACE
  ├─ SPAN: Retrieval (调用1)
  └─ SPAN: Retrieval (调用2)
```

**v2.x 及之后**：每次调用创建独立的 Trace（更合理的默认行为）
```
TRACE_1
  └─ SPAN: Retrieval (调用1)

TRACE_2
  └─ SPAN: Retrieval (调用2)
```

如果需要将多次调用合并到一个 Trace，需要使用 Langfuse SDK：

```python
from langfuse import Langfuse

langfuse = Langfuse()
trace = langfuse.trace()
handler = trace.get_langchain_handler()  # 获取关联到特定 trace 的 handler
```

---

## 四、完整集成示例

### 4.1 Python 完整示例

#### 4.1.1 环境配置

```bash
# 安装依赖
pip install langfuse langchain langchain_openai langgraph
```

#### 4.1.2 环境变量设置

```env
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com  # 🇪🇺 EU region
# LANGFUSE_BASE_URL=https://us.cloud.langfuse.com  # 🇺🇸 US region

OPENAI_API_KEY=sk-proj-...
```

#### 4.1.3 代码实现

```python
from langfuse import Langfuse, get_client
from langfuse.langchain import CallbackHandler
from langchain.agents import create_agent

# 1. 初始化 Langfuse 客户端（应用启动时执行一次）
Langfuse(
    public_key="pk-lf-...",
    secret_key="sk-lf-...",
    host="https://cloud.langfuse.com"
)

# 2. 创建 CallbackHandler
langfuse = get_client()
langfuse_handler = CallbackHandler()

# 3. 定义工具函数
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together and return the result."""
    return a + b

# 4. 创建 Agent
agent = create_agent(
    model="openai:gpt-5-mini",
    tools=[add_numbers],
    system_prompt="You are a helpful math tutor who can do calculations using the provided tools.",
)

# 5. 运行 Agent（传递 CallbackHandler）
response = agent.invoke(
    {"messages": [{"role": "user", "content": "what is 42 + 58?"}]},
    config={"callbacks": [langfuse_handler]}
)

# 6. 在短生命周期脚本中，确保刷新事件
langfuse.flush()
```

### 4.2 LangGraph 集成

LangGraph 的集成方式与 LangChain 相同，只需将 `langfuse_handler` 传递给 Agent 调用：

```python
# LangGraph 示例
graph = create_graph(...)
app = graph.compile()

# 调用时传递 CallbackHandler
result = app.invoke(
    {"messages": [...]},
    config={"callbacks": [langfuse_handler]}
)
```

---

## 五、高级特性

### 5.1 分布式追踪

#### 5.1.1 Trace ID 传递

Langfuse 支持分布式追踪，可以在多个服务间传递 Trace ID：

```python
# 服务 A：创建 Trace 并获取 Trace ID
from langfuse import get_client

langfuse = get_client()
trace = langfuse.trace(name="service_a_operation")
trace_id = trace.id

# 将 trace_id 传递给服务 B（通过 HTTP header、消息队列等）

# 服务 B：使用相同的 Trace ID
handler = CallbackHandler()
# 通过 metadata 传递 trace_id
chain.invoke(
    {"input": "..."},
    config={
        "callbacks": [handler],
        "metadata": {"langfuse_trace_id": trace_id}
    }
)
```

#### 5.1.2 上下文变量（ContextVar）

v3.x 版本使用 `contextvars` 自动管理上下文：

```python
from langfuse import get_client

langfuse = get_client()

# 创建活动的 Span
with langfuse.start_as_current_span(name="parent_operation") as span:
    # 在这个上下文中，所有 CallbackHandler 都会自动关联到这个 span
    handler = CallbackHandler()
    chain.invoke({"input": "..."}, config={"callbacks": [handler]})
    # 子操作会自动成为当前 span 的子 span
```

### 5.2 自定义观察名称

可以通过 LangChain 的 `metadata` 自定义观察名称：

```python
chain.invoke(
    {"input": "..."},
    config={
        "callbacks": [handler],
        "metadata": {
            "langfuse_name": "custom_operation_name"
        }
    }
)
```

### 5.3 评分（Scoring）

可以在 Langfuse UI 中为 Trace 添加评分，也可以通过 API：

```python
from langfuse import get_client

langfuse = get_client()
trace = langfuse.trace(id="trace_id")
trace.score(name="user_satisfaction", value=0.9)
```

### 5.4 队列和刷新

#### 5.4.1 自动刷新

Langfuse SDK 默认会在后台自动刷新事件，但在短生命周期脚本中，建议手动刷新：

```python
from langfuse import get_client

langfuse = get_client()
# ... 执行操作 ...
langfuse.flush()  # 确保所有事件都已发送
```

#### 5.4.2 服务器less 环境

在服务器less 环境（如 AWS Lambda）中，确保在函数结束前刷新：

```python
def lambda_handler(event, context):
    langfuse = get_client()
    handler = CallbackHandler()
    
    try:
        result = chain.invoke({...}, config={"callbacks": [handler]})
        return result
    finally:
        langfuse.flush()  # 确保事件发送
```

---

## 六、项目中的实际应用

### 6.1 项目中的实现方式

根据项目代码分析，当前实现方式如下：

#### 6.1.1 Handler 创建

```python
# cursor_test/langfuse/02flow/langfuse_local/handler.py
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

def create_langfuse_handler() -> Optional[LangfuseCallbackHandler]:
    """创建 Langfuse CallbackHandler"""
    # 检查配置
    if not settings.LANGFUSE_ENABLED:
        return None
    
    # 确保全局客户端已初始化
    _get_langfuse_client()
    
    # 尝试从 ContextVar 获取 trace_id
    trace_id = get_current_trace_id()
    
    # 创建 Handler（v3.x 会自动关联当前活动的 trace）
    handler = LangfuseCallbackHandler()
    return handler
```

#### 6.1.2 在节点中使用

```python
# cursor_test/langfuse/02flow/flows/builder.py
def agent_node(state):
    # 获取 trace_id
    trace_id = get_current_trace_id()
    
    # 创建 Langfuse Handler
    langfuse_handler = create_langfuse_handler()
    if langfuse_handler:
        callbacks.append(langfuse_handler)
    
    # 创建子 Span（用于设置节点名称）
    langfuse_client = get_langfuse_client()
    if langfuse_client and trace_id:
        with langfuse_client.start_as_current_span(
            name=node_name,
            trace_id=trace_id
        ):
            # 执行 Agent 调用
            result = agent.invoke(state, config={"callbacks": callbacks})
    
    return result
```

#### 6.1.3 LLM 调用集成

```python
# cursor_test/langfuse/02flow/llm/client.py
def call_llm(..., callbacks: Optional[List[BaseCallbackHandler]] = None):
    # 自动添加 Langfuse 回调（如果未手动提供）
    if callbacks is None:
        callbacks = []
    
    langfuse_handler = create_langfuse_handler()
    if langfuse_handler:
        callbacks.append(langfuse_handler)
    
    # 调用 LLM
    response = llm.invoke(messages, config={"callbacks": callbacks})
    return response
```

### 6.2 关键设计点

1. **上下文管理**：使用 `contextvars` 和 `ContextVar` 来传递 `trace_id`
2. **自动关联**：`CallbackHandler` 自动检测当前活动的 Trace/Span
3. **分层记录**：
   - 顶层：使用 `start_as_current_span` 创建节点级别的 Span
   - 底层：`CallbackHandler` 自动记录 LLM 调用、工具调用等
4. **容错处理**：如果 Langfuse 不可用，不影响主流程执行

---

## 七、常见问题与最佳实践

### 7.1 常见问题

#### Q1: 如何自定义观察名称？

**A**: 通过 LangChain 的 `metadata` 传递 `langfuse_name`：

```python
config = {
    "callbacks": [handler],
    "metadata": {"langfuse_name": "custom_name"}
}
```

#### Q2: 如何将多次调用合并到一个 Trace？

**A**: 使用 Langfuse SDK 创建 Trace，然后获取关联的 Handler：

```python
from langfuse import get_client

langfuse = get_client()
trace = langfuse.trace(name="multi_invocation_trace")
handler = trace.get_langchain_handler()  # v3.x 可能不支持，需要使用其他方式
```

#### Q3: 如何传递 user_id 和 session_id？

**A**: 通过 `metadata` 或使用 `span.update_trace()`：

```python
# 方式一：metadata
config = {
    "callbacks": [handler],
    "metadata": {
        "langfuse_user_id": "user_123",
        "langfuse_session_id": "session_456"
    }
}

# 方式二：span 更新
with langfuse.start_as_current_span(...) as span:
    span.update_trace(user_id="user_123", session_id="session_456")
    chain.invoke({...}, config={"callbacks": [handler]})
```

### 7.2 最佳实践

1. **初始化时机**：在应用启动时初始化 Langfuse 客户端，而不是每次调用时
2. **Handler 复用**：可以创建一次 Handler 实例，在多次调用中复用
3. **刷新事件**：在短生命周期脚本中，确保调用 `flush()` 方法
4. **错误处理**：确保 Langfuse 的失败不会影响主业务流程
5. **版本管理**：使用 v3.x 版本，享受更好的上下文管理和单例模式

---

## 八、总结

### 8.1 核心原理

Langfuse 通过 LangChain 的**回调机制**实现集成：
1. `CallbackHandler` 实现 LangChain 的回调接口
2. 在链执行过程中自动捕获事件
3. 转换为 Langfuse 的 Trace/Span/Generation 结构
4. 通过 `contextvars` 管理上下文，实现自动关联

### 8.2 关键优势

1. **自动化**：无需手动记录每个步骤，自动捕获执行过程
2. **完整性**：捕获 LLM 调用、工具使用、检索操作等所有细节
3. **可观测性**：提供延迟、成本、输入输出等完整指标
4. **易用性**：只需传递一个 Handler，即可实现完整追踪

### 8.3 版本建议

- **推荐使用 v3.x**：更好的上下文管理、单例模式、更简洁的 API
- **迁移路径**：从 v2.x 迁移到 v3.x 需要修改导入和初始化方式

---

## 参考资料

1. [Langfuse 官方文档 - LangChain & LangGraph Integration](https://langfuse.com/integrations/frameworks/langchain)
2. [Langfuse 博客 - Langchain Integration](https://langfuse.com/blog/langchain-integration)
3. [LangChain 官方文档 - Callbacks](https://python.langchain.com/docs/modules/callbacks/)
4. 项目代码：
   - `cursor_test/langfuse/02flow/langfuse_local/handler.py`
   - `cursor_test/langfuse/02flow/flows/builder.py`
   - `cursor_test/langfuse/02flow/llm/client.py`

---

*最后更新时间：2025-01-06*

