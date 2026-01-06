# Langfuse `start_as_current_span` vs `start_as_current_observation` 区别说明

## 概述

Langfuse SDK 提供了两个方法来创建追踪上下文：
1. `start_as_current_span()` - 专门用于创建 Span 类型
2. `start_as_current_observation()` - 通用的方法，可以创建多种类型的 observation

## 核心区别

### 1. `start_as_current_span()` - 专用方法

**特点**：
- ✅ **专门用于创建 Span**：只能创建 Span 类型的 observation
- ✅ **简单直接**：参数较少，使用简单
- ✅ **类型明确**：返回类型固定为 `LangfuseSpan`

**方法签名**：
```python
def start_as_current_span(
    self,
    *,
    trace_context: Optional[TraceContext] = None,
    name: str,
    input: Optional[Any] = None,
    output: Optional[Any] = None,
    metadata: Optional[Any] = None,
    version: Optional[str] = None,
    level: Optional[SpanLevel] = None,
    status_message: Optional[str] = None,
    end_on_exit: Optional[bool] = None,
) -> _AgnosticContextManager[LangfuseSpan]
```

**使用示例**：
```python
with client.start_as_current_span(
    name="节点A",
    input={"data": "some data"},
    metadata={"key": "value"}
):
    # 执行操作
    result = do_something()
```

### 2. `start_as_current_observation()` - 通用方法

**特点**：
- ✅ **支持多种类型**：可以创建 span, generation, tool, agent, chain, retriever, evaluator, embedding, guardrail
- ✅ **功能更强大**：支持更多参数，特别是针对 LLM 调用的参数
- ✅ **灵活性强**：通过 `as_type` 参数指定类型，默认为 "span"

**方法签名**：
```python
def start_as_current_observation(
    self,
    *,
    trace_context: Optional[TraceContext] = None,
    name: str,
    as_type: ObservationTypeLiteralNoEvent = "span",  # 关键参数
    input: Optional[Any] = None,
    output: Optional[Any] = None,
    metadata: Optional[Any] = None,
    version: Optional[str] = None,
    level: Optional[SpanLevel] = None,
    status_message: Optional[str] = None,
    # 以下参数仅在 as_type="generation" 或 "embedding" 时可用
    completion_start_time: Optional[datetime] = None,
    model: Optional[str] = None,
    model_parameters: Optional[Dict[str, MapValue]] = None,
    usage_details: Optional[Dict[str, int]] = None,
    cost_details: Optional[Dict[str, float]] = None,
    prompt: Optional[PromptClient] = None,
    end_on_exit: Optional[bool] = None,
) -> Union[
    LangfuseGeneration,
    LangfuseSpan,
    LangfuseAgent,
    LangfuseTool,
    LangfuseChain,
    LangfuseRetriever,
    LangfuseEvaluator,
    LangfuseEmbedding,
    LangfuseGuardrail,
]
```

**使用示例**：

1. **创建 Span**（与 `start_as_current_span()` 等价）：
```python
with client.start_as_current_observation(
    name="节点A",
    as_type="span",  # 默认值，可以省略
    input={"data": "some data"}
):
    result = do_something()
```

2. **创建 Generation**（用于 LLM 调用追踪）：
```python
with client.start_as_current_observation(
    name="llm-call",
    as_type="generation",
    model="gpt-4",
    model_parameters={"temperature": 0.7},
    usage_details={"prompt_tokens": 100, "completion_tokens": 50},
    cost_details={"total_cost": 0.002}
) as generation:
    response = llm.generate(prompt)
    generation.update(output=response)
```

3. **创建 Tool**（用于工具调用追踪）：
```python
with client.start_as_current_observation(
    name="web-search",
    as_type="tool",
    input={"query": "Python tutorial"}
) as tool:
    results = search_web(query)
    tool.update(output=results)
```

## 对比总结

| 特性 | `start_as_current_span()` | `start_as_current_observation()` |
|------|---------------------------|----------------------------------|
| **类型支持** | 仅 Span | Span, Generation, Tool, Agent, Chain, Retriever, Evaluator, Embedding, Guardrail |
| **参数数量** | 较少（8个） | 较多（17个） |
| **LLM 专用参数** | ❌ 不支持 | ✅ 支持（model, usage_details, cost_details 等） |
| **使用场景** | 简单的流程追踪 | 复杂的追踪，特别是需要追踪 LLM 调用、工具调用等 |
| **返回类型** | `LangfuseSpan` | 根据 `as_type` 返回不同类型 |
| **易用性** | ✅ 更简单 | ⚠️ 需要指定 `as_type` |

## 实际应用建议

### 使用 `start_as_current_span()` 的场景

1. **简单的流程追踪**：
```python
# 追踪业务流程节点
with client.start_as_current_span(name="处理订单"):
    process_order()
```

2. **嵌套的 Span 结构**（如我们的示例）：
```python
with client.start_as_current_span(name="Trace"):
    with client.start_as_current_span(name="节点A"):
        with client.start_as_current_span(name="节点A-1"):
            do_a1()
```

### 使用 `start_as_current_observation()` 的场景

1. **追踪 LLM 调用**：
```python
with client.start_as_current_observation(
    name="chat-completion",
    as_type="generation",
    model="gpt-4",
    model_parameters={"temperature": 0.7}
) as gen:
    response = chat_model.invoke(messages)
    gen.update(output=response.content)
```

2. **追踪工具调用**：
```python
with client.start_as_current_observation(
    name="record-blood-pressure",
    as_type="tool",
    input={"systolic": 120, "diastolic": 80}
) as tool:
    result = record_blood_pressure(120, 80)
    tool.update(output=result)
```

3. **需要更详细的元数据**：
```python
with client.start_as_current_observation(
    name="complex-operation",
    as_type="span",
    metadata={"detailed": "information"},
    version="1.0.0"
):
    complex_operation()
```

## 在我们的项目中的应用

### 当前使用方式（`test_flow_trace.py`）

我们使用 `start_as_current_span()` 来创建流程追踪，这是正确的选择，因为：

1. **我们只需要 Span 类型**：我们的流程追踪不需要区分不同的 observation 类型
2. **简单明了**：代码更简洁，易于理解
3. **性能更好**：参数更少，调用更轻量

```python
# 当前代码（推荐）
with client.start_as_current_span(**trace_params):
    # 执行流程
    pass
```

### 如果需要追踪 LLM 调用

如果将来需要在流程中追踪 LLM 调用，可以使用 `start_as_current_observation()`：

```python
with client.start_as_current_span(name="Trace"):
    # 普通节点
    with client.start_as_current_span(name="节点A"):
        do_a()
    
    # LLM 调用节点
    with client.start_as_current_observation(
        name="llm-call",
        as_type="generation",
        model="gpt-4"
    ) as gen:
        response = llm.invoke(messages)
        gen.update(output=response)
```

## 总结

- **`start_as_current_span()`**：适合简单的流程追踪，代码简洁
- **`start_as_current_observation()`**：适合复杂的追踪场景，特别是需要追踪 LLM 调用、工具调用等

在我们的流程追踪示例中，使用 `start_as_current_span()` 是最合适的选择。

