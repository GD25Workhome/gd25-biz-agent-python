# Langfuse 可观测性平台详解

## 📚 目录
1. [什么是 Langfuse](#什么是-langfuse)
2. [核心概念](#核心概念)
3. [Langfuse 3.x 架构](#langfuse-3x-架构)
4. [与 LangGraph/LangChain 集成](#与-langgraphlangchain-集成)
5. [项目中的实际应用](#项目中的实际应用)
6. [常见问题与解决方案](#常见问题与解决方案)
7. [最佳实践](#最佳实践)

---

## 什么是 Langfuse

**Langfuse** 是一个开源的 **LLM 应用可观测性平台**，专门用于追踪、分析和优化 LLM（大型语言模型）应用程序。

### 核心功能

1. **可观测性（Observability）**
   - 全链路追踪：记录用户与 LLM 应用的完整交互过程
   - 输入/输出记录：保存每次调用的 prompt 和 response
   - 中间步骤追踪：记录 RAG 流程的检索、生成等阶段
   - 性能分析：耗时统计、tokens 使用情况

2. **提示管理（Prompt Management）**
   - 集中存储提示词模板
   - 版本控制和团队协作
   - A/B 测试支持

3. **评估（Evaluation）**
   - LLM 作为评判者
   - 用户反馈收集
   - 人工标注支持
   - 自定义评估方法

### 为什么需要 Langfuse

在 LLM 应用开发中，我们经常遇到以下问题：

- **调试困难**：不知道 LLM 为什么返回某个结果
- **成本不透明**：不清楚每次调用消耗了多少 tokens
- **性能瓶颈**：不知道哪个环节最耗时
- **提示词迭代**：难以对比不同提示词的效果
- **生产监控**：无法追踪生产环境中的问题

Langfuse 解决了这些问题，提供了完整的可观测性解决方案。

---

## 核心概念

### 1. Trace（追踪）

**Trace** 是 Langfuse 中最顶层的概念，代表**一次完整的用户交互或业务流程**。

#### 特点

- **唯一标识**：每个 Trace 有唯一的 ID
- **元数据**：可以附加用户 ID、会话 ID、版本号等信息
- **层级结构**：包含多个 Span 和 Generation
- **生命周期**：从开始到结束的完整过程

#### 示例

```python
from langfuse import Langfuse

langfuse = Langfuse()

# 创建一个 Trace
trace = langfuse.start_span(
    name="用户查询处理",
    metadata={
        "user_id": "user_123",
        "session_id": "session_456",
        "version": "v1.0"
    }
)
```

#### 在项目中的应用

- 一次完整的聊天请求 = 一个 Trace
- 一次路由图执行 = 一个 Trace
- 一次多轮对话流程 = 一个 Trace

---

### 2. Span（跨度）

**Span** 是 Trace 中的**一个操作单元**，代表执行过程中的一个步骤或节点。

#### 特点

- **层级关系**：Span 可以嵌套（父 Span 包含子 Span）
- **输入/输出**：记录操作的输入和输出
- **元数据**：可以附加额外的上下文信息
- **耗时统计**：自动记录执行时间

#### 示例

```python
# 在 Trace 中创建 Span
span = langfuse.start_span(
    name="路由节点",
    input={"message": "用户消息"},
    metadata={"node_type": "router"}
)

# 执行操作
result = router_node.invoke(input_data)

# 更新 Span
span.update(output=result)
span.end()
```

#### 在项目中的应用

- LangGraph 的每个节点 = 一个 Span
- 路由决策 = 一个 Span
- 意图识别 = 一个 Span
- 工具调用 = 一个 Span

---

### 3. Generation（生成）

**Generation** 是 Span 的一种特殊类型，专门用于追踪 **LLM 调用**。

#### 特点

- **LLM 专用**：专门记录 LLM 的输入和输出
- **Tokens 统计**：记录 prompt tokens、completion tokens、total tokens
- **模型信息**：记录使用的模型名称和参数
- **成本计算**：根据 tokens 和模型价格计算成本

#### 示例

```python
# 创建 Generation Span
generation = trace.start_generation(
    name="LLM调用",
    model="deepseek-chat",
    input="用户的问题",
    metadata={"temperature": 0.7}
)

# 调用 LLM
response = llm.invoke(messages)

# 更新 Generation
generation.update(
    output=response.content,
    usage={
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150
    }
)
generation.end()
```

#### 在项目中的应用

- 每次 LLM 调用 = 一个 Generation
- 意图识别 LLM 调用 = 一个 Generation
- 智能体 LLM 调用 = 一个 Generation
- 澄清意图 LLM 调用 = 一个 Generation

---

### 4. 层级关系

```
Trace（追踪）
├── Span（路由节点）
│   ├── Generation（意图识别 LLM 调用）
│   └── Span（工具调用）
├── Span（智能体节点）
│   └── Generation（智能体 LLM 调用）
└── Span（响应处理）
```

---

## Langfuse 3.x 架构

### OpenTelemetry 集成

Langfuse 3.x 基于 **OpenTelemetry** 标准，提供了更好的可观测性支持。

#### 优势

- **标准化**：遵循 OpenTelemetry 标准，与其他工具兼容
- **自动追踪**：可以自动追踪 LangChain/LangGraph 的调用
- **性能优化**：批量发送数据，减少网络开销
- **灵活配置**：支持采样率、环境隔离等高级功能

#### 初始化

```python
from langfuse import Langfuse

# 方式1：从环境变量读取
langfuse = Langfuse()

# 方式2：显式传入参数
langfuse = Langfuse(
    public_key="pk-lf-...",
    secret_key="sk-lf-...",
    host="https://cloud.langfuse.com"
)
```

#### 环境变量

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com  # 或 LANGFUSE_HOST
```

---

## 与 LangGraph/LangChain 集成

### 1. 手动追踪方式

在 LangGraph 节点中手动创建 Span 和 Generation。

#### 优点

- **精确控制**：可以精确控制追踪的粒度
- **自定义元数据**：可以添加业务相关的元数据
- **灵活性强**：不依赖框架的自动追踪

#### 缺点

- **代码侵入**：需要在每个节点中添加追踪代码
- **维护成本**：追踪逻辑分散在业务代码中

#### 示例

```python
def router_node(state: RouterState) -> RouterState:
    # 创建 Span
    span = langfuse_client.start_span(
        name="router_node",
        input=state
    )
    
    try:
        # 执行路由逻辑
        result = do_routing(state)
        
        # 更新 Span
        span.update(output=result)
        return result
    finally:
        span.end()
```

---

### 2. 自动追踪方式（推荐）

利用 Langfuse 的自动追踪功能，通过回调机制追踪 LangChain/LangGraph 调用。

#### 优点

- **零侵入**：不需要修改业务代码
- **自动记录**：自动记录所有 LLM 调用
- **统一管理**：追踪逻辑集中管理

#### 缺点

- **配置复杂**：需要正确配置回调处理器
- **灵活性较低**：难以添加自定义元数据

#### 示例（Langfuse 2.x 方式，3.x 可能不同）

```python
from langfuse.langchain import LangfuseCallbackHandler

# 创建回调处理器
callback = LangfuseCallbackHandler()

# 在调用时传入
config = RunnableConfig(callbacks=[callback])
result = graph.invoke(state, config=config)
```

---

### 3. 混合方式（项目推荐）

结合手动追踪和自动追踪，在关键节点手动创建 Span，LLM 调用自动追踪。

#### 示例

```python
def agent_node(state: RouterState) -> RouterState:
    # 手动创建节点 Span
    span = langfuse_client.start_span(
        name="agent_node",
        input=state,
        metadata={"agent_name": "blood_pressure_agent"}
    )
    
    try:
        # LLM 调用会自动被追踪（如果配置了自动追踪）
        llm = get_llm()
        response = llm.invoke(messages)
        
        result = process_response(response)
        
        span.update(output=result)
        return result
    finally:
        span.end()
```

---

## 项目中的实际应用

### 1. 测试场景

在测试代码中，我们使用手动追踪方式：

```python
# test_01_simple_graph.py
def node_a(state: SimpleGraphState) -> SimpleGraphState:
    # 手动创建 Span
    if _langfuse_client:
        span = _langfuse_client.start_span(name="node_a", input=state)
    
    # 执行逻辑
    result = do_something(state)
    
    # 更新并结束 Span
    if _langfuse_client:
        span.update(output=result)
        span.end()
    
    return result
```

### 2. LLM 调用追踪

在测试2中，我们手动创建 Generation Span：

```python
# test_02_llm_graph.py
def call_llm_node(state: LLMGraphState) -> LLMGraphState:
    # 创建 Generation Span
    generation = trace.start_generation(
        name="llm_call",
        model="deepseek-chat",
        input=input_text
    )
    
    # 调用 LLM
    response = llm.invoke(messages)
    
    # 更新 Generation
    generation.update(
        output=response.content,
        usage=extract_usage(response)
    )
    generation.end()
```

### 3. 生产环境集成建议

在生产环境中，建议：

1. **在路由图创建时初始化 Langfuse**
   ```python
   # app/main.py
   langfuse = Langfuse()
   app.state.langfuse = langfuse
   ```

2. **在 API 路由中创建 Trace**
   ```python
   # app/api/routes.py
   @router.post("/chat")
   async def chat(request: ChatRequest):
       langfuse = app.state.langfuse
       trace = langfuse.start_span(
           name="chat_request",
           metadata={
               "user_id": request.user_id,
               "session_id": request.session_id
           }
       )
       
       try:
           result = await router_graph.ainvoke(state, config)
           trace.update(output=result)
           return result
       finally:
           trace.end()
           langfuse.flush()
   ```

3. **在节点中创建 Span**
   ```python
   # domain/router/node.py
   async def route_node(state: RouterState) -> RouterState:
       # 从上下文获取 Langfuse 客户端
       langfuse = get_langfuse_client()
       span = langfuse.start_span(name="route_node", input=state)
       
       try:
           # 执行路由逻辑
           result = await do_routing(state)
           span.update(output=result)
           return result
       finally:
           span.end()
   ```

---

## 常见问题与解决方案

### 1. 为什么看不到 LLM 调用的追踪？

**问题**：在 Dashboard 中看不到 Generation Span。

**原因**：
- 没有创建 Generation Span
- LLM 调用不在 Trace 上下文中
- 回调处理器配置不正确

**解决方案**：

```python
# 方式1：手动创建 Generation
generation = trace.start_generation(
    name="llm_call",
    model="deepseek-chat",
    input=prompt
)
response = llm.invoke(messages)
generation.update(output=response.content)
generation.end()

# 方式2：确保在 Trace 上下文中调用
with trace:
    response = llm.invoke(messages)
```

---

### 2. 如何获取 Tokens 使用情况？

**问题**：Generation Span 中没有显示 tokens 统计。

**原因**：
- LLM 响应中没有包含 usage 信息
- 没有正确提取 usage 信息

**解决方案**：

```python
# 从 LLM 响应中提取 usage
response = llm.invoke(messages)

usage = None
if hasattr(response, 'response_metadata') and response.response_metadata:
    usage_info = response.response_metadata.get('token_usage', {})
    if usage_info:
        usage = {
            "prompt_tokens": usage_info.get("prompt_tokens", 0),
            "completion_tokens": usage_info.get("completion_tokens", 0),
            "total_tokens": usage_info.get("total_tokens", 0)
        }

generation.update(output=response.content, usage=usage)
```

---

### 3. 数据没有发送到 Langfuse？

**问题**：代码执行了，但 Dashboard 中没有看到数据。

**原因**：
- 没有调用 `flush()`
- 网络问题
- 凭据配置错误

**解决方案**：

```python
# 确保在程序结束前调用 flush
langfuse.flush()

# 或者在关键位置调用
try:
    result = graph.invoke(state)
finally:
    langfuse.flush()
```

---

### 4. 如何追踪异步调用？

**问题**：在异步函数中如何正确追踪。

**解决方案**：

```python
async def async_node(state: RouterState) -> RouterState:
    span = langfuse_client.start_span(name="async_node", input=state)
    
    try:
        result = await async_operation(state)
        span.update(output=result)
        return result
    finally:
        span.end()
```

---

### 5. 如何添加自定义元数据？

**问题**：想在 Trace/Span 中添加业务相关的信息。

**解决方案**：

```python
# 在创建时添加
trace = langfuse.start_span(
    name="user_query",
    metadata={
        "user_id": "user_123",
        "session_id": "session_456",
        "feature": "blood_pressure",
        "version": "v1.0"
    }
)

# 在运行时更新
span.update(metadata={"additional_info": "value"})
```

---

## 最佳实践

### 1. Trace 命名规范

- **清晰明确**：使用描述性的名称，如 `chat_request`、`blood_pressure_recording`
- **统一格式**：使用下划线或连字符，保持一致性
- **包含上下文**：在名称中包含关键信息，如 `route_to_blood_pressure_agent`

### 2. Span 粒度控制

- **不要太细**：避免为每个小操作创建 Span
- **不要太粗**：关键业务节点应该有独立的 Span
- **合理嵌套**：利用 Span 的嵌套关系组织代码

### 3. 元数据管理

- **用户标识**：始终包含 `user_id` 和 `session_id`
- **版本信息**：记录代码版本，便于问题定位
- **业务上下文**：添加业务相关的元数据，如 `agent_name`、`intent`

### 4. 性能优化

- **批量发送**：Langfuse 会自动批量发送数据，无需手动优化
- **采样率**：在生产环境中可以设置采样率，减少数据量
- **异步处理**：追踪操作应该是异步的，不影响业务性能

### 5. 错误处理

- **异常记录**：在 Span 中记录异常信息
- **状态标记**：使用 `level` 和 `status_message` 标记错误
- **优雅降级**：追踪失败不应该影响业务逻辑

```python
try:
    result = operation()
    span.update(output=result)
except Exception as e:
    span.update(
        level="ERROR",
        status_message=str(e),
        metadata={"error_type": type(e).__name__}
    )
    raise
finally:
    span.end()
```

---

## 参考资料

### 官方文档

- **Langfuse 官方文档**：https://langfuse.com/docs
- **Python SDK 文档**：https://langfuse.com/docs/sdk/python
- **OpenTelemetry 文档**：https://opentelemetry.io/docs/

### 项目相关

- **测试代码**：`cursor_test/M3_test/langfuse/`
- **学习方案**：`cursor_test/M3_test/langfuse/Langfuse对接学习方案.md`
- **对接说明**：`cursor_test/M3_test/langfuse/千问的对接说明.md`

### 关键概念速查

| 概念 | 说明 | 使用场景 |
|------|------|----------|
| **Trace** | 一次完整的业务流程 | 一次聊天请求、一次路由图执行 |
| **Span** | 一个操作单元 | LangGraph 节点、路由决策、工具调用 |
| **Generation** | LLM 调用追踪 | 意图识别、智能体回复、澄清询问 |
| **Metadata** | 附加的上下文信息 | 用户ID、会话ID、版本号、业务参数 |

---

## 总结

Langfuse 是一个强大的 LLM 应用可观测性平台，通过 Trace、Span、Generation 等概念，提供了完整的追踪和分析能力。

### 关键要点

1. **Trace 是顶层概念**：代表一次完整的业务流程
2. **Span 是操作单元**：代表执行过程中的一个步骤
3. **Generation 是 LLM 专用**：专门追踪 LLM 调用
4. **手动追踪更灵活**：可以精确控制追踪粒度
5. **自动追踪更便捷**：减少代码侵入

### 下一步

1. 在项目中集成 Langfuse
2. 在关键节点添加追踪
3. 在 Dashboard 中分析数据
4. 根据数据优化应用性能

---

*最后更新：2025-12-22*

