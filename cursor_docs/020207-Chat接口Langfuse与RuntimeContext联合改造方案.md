# Chat 接口 Langfuse 与 RuntimeContext 联合改造方案

> 本文档将「Langfuse start_as_current_span 嵌套方案」与「020206 方案 A：config.metadata」结合，给出 Chat 接口的联合改造实施指南。

**文档版本**：V1.0  
**创建时间**：2025-02-02  
**关联文档**：`020206-Chat接口Langfuse-Metadata评审与升级建议.md`

---

## 一、改造目标

1. **保留 RuntimeContext**：确保流程内工具（如 blood_pressure_tool）能通过 `get_token_id()` 等获取 token_id、session_id、trace_id
2. **采用 Langfuse 官方 span 模式**：使用 `with langfuse.start_as_current_span() as span`，支持 `span.update_trace()` 动态设置 Trace 属性及 output
3. **应用方案 A 的 config.metadata**：通过 LangChain config 传入 `langfuse_user_id`、`langfuse_session_id`、`langfuse_tags` 等，符合官方推荐、便于子 Span 传播

---

## 二、三层结构关系

```
┌─────────────────────────────────────────────────────────────────┐
│ 第 1 层：Langfuse Span（可观测性）                                │
│   with langfuse.start_as_current_span(...) as span               │
│   - 创建 Trace，设置 user_id、session_id、metadata                │
│   - 支持 span.update_trace(output=...) 在 invoke 后写入 output    │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 第 2 层：RuntimeContext（工具上下文）                             │
│   with RuntimeContext(token_id=..., session_id=..., trace_id=...)│
│   - 工具通过 get_token_id() 等获取运行时信息                       │
│   - 不可移除，否则工具无法识别用户身份                             │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 第 3 层：config（LangChain 调用配置）                             │
│   config = { callbacks, metadata, configurable }                 │
│   - metadata：langfuse_user_id、langfuse_session_id、tags        │
│   - 供 Langfuse CallbackHandler 传播到子 Span                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、改造前后对比

### 3.1 改造前（当前实现）

```python
langfuse_handler = create_langfuse_handler(context={"trace_id": request.trace_id})

with RuntimeContext(
    token_id=request.token_id,
    session_id=request.session_id,
    trace_id=request.trace_id
):
    config = {"configurable": {"thread_id": request.session_id}}
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
    result = await graph.ainvoke(initial_state, config)

# 提取 response_text...
```

**缺失**：
- 未使用 `start_as_current_span`，无法在 invoke 后通过 `span.update_trace(output=...)` 写入 output
- 未设置 `langfuse_user_id`、`langfuse_session_id`、`langfuse_tags`，Langfuse 中按用户/会话筛选受限

### 3.2 改造后（联合方案）

```python
from backend.infrastructure.observability.langfuse_handler import (
    create_langfuse_handler,
    get_langfuse_client,
    normalize_langfuse_trace_id,
)

# 1. 创建 Langfuse Handler（需在 span 外，因 trace_context 依赖 trace_id）
langfuse_handler = create_langfuse_handler(context={"trace_id": request.trace_id})

# 2. 构建 config（含方案 A 的 metadata）
config = {"configurable": {"thread_id": request.session_id}}
if langfuse_handler:
    config["callbacks"] = [langfuse_handler]
    config["metadata"] = {
        "langfuse_user_id": request.token_id or "",
        "langfuse_session_id": request.session_id,
        "langfuse_tags": ["chat", "api"],
        "source": "chat_api",
        "message_length": str(len(request.message)),
        "history_count": str(len(request.conversation_history) or 0),
    }

# 3. 第 1 层：Langfuse Span（仅当 Langfuse 可用时）
langfuse_client = get_langfuse_client()
if langfuse_client:
    normalized_trace_id = normalize_langfuse_trace_id(request.trace_id)
    with langfuse_client.start_as_current_span(
        name="chat-request",
        trace_context={"trace_id": normalized_trace_id},
    ) as span:
        span.update_trace(
            user_id=request.token_id,
            session_id=request.session_id,
            metadata={
                "source": "chat_api",
                "message_length": len(request.message),
                "history_count": len(request.conversation_history) or 0,
            },
        )
        # 第 2 层：RuntimeContext
        with RuntimeContext(
            token_id=request.token_id,
            session_id=request.session_id,
            trace_id=request.trace_id
        ):
            result = await graph.ainvoke(initial_state, config)
        # 提取 response_text...
        span.update_trace(output={"response": response_text})
else:
    # Langfuse 不可用时，仅保留 RuntimeContext
    with RuntimeContext(
        token_id=request.token_id,
        session_id=request.session_id,
        trace_id=request.trace_id
    ):
        result = await graph.ainvoke(initial_state, config)
    # 提取 response_text...
```

---

## 四、实施步骤

### 4.1 步骤 1：确认 langfuse_handler 可用接口

- `get_langfuse_client`：已在 `__init__.py` 导出，可直接从 `langfuse_handler` 或 `observability` 导入
- `normalize_langfuse_trace_id`：当前仅在 `langfuse_handler` 模块内，需从 `backend.infrastructure.observability.langfuse_handler` 直接导入，或按需加入 `__init__.py` 导出

### 4.2 步骤 2：修改 chat.py

1. **导入**：增加 `get_langfuse_client`、`normalize_langfuse_trace_id`
2. **config 构建**：在 `if langfuse_handler` 分支内增加 `config["metadata"]`（方案 A）
3. **嵌套结构**：
   - 若 `langfuse_client` 存在：`with start_as_current_span` → `with RuntimeContext` → `graph.ainvoke` → `span.update_trace(output=...)`
   - 若不存在：仅 `with RuntimeContext` → `graph.ainvoke`

### 4.3 步骤 3：验证

1. **工具调用**：确认 `get_token_id()` 在工具内仍能正确返回值
2. **Langfuse Trace**：在 Langfuse UI 中确认 Trace 具备 user_id、session_id、metadata、output
3. **按会话/用户筛选**：验证可按 session_id、user_id 过滤 Trace

---

## 五、注意事项

### 5.1 metadata 值限制

Langfuse 对 metadata 值有 **≤ 200 字符** 限制，键仅限字母数字。`message_length`、`history_count` 等建议转为字符串，超长内容需截断。

### 5.2 trace_id 一致性

`create_langfuse_handler(context={"trace_id": request.trace_id})` 与 `start_as_current_span(trace_context={"trace_id": normalized_trace_id})` 必须使用**同一 trace_id**（normalize 后格式一致），否则 CallbackHandler 可能创建新 Trace 而非关联到当前 span。

### 5.3 Langfuse 不可用时的降级

当 `get_langfuse_client()` 返回 `None` 时，不进入 `start_as_current_span`，仅保留 `RuntimeContext` 与 `graph.ainvoke`，保证业务逻辑不受影响。

### 5.4 嵌套顺序

必须保持：**Langfuse Span 在外，RuntimeContext 在内**。若颠倒，工具执行时可能尚未进入 RuntimeContext，导致 `get_token_id()` 返回 `None`。

---

## 六、方案 A 与 Span 模式的互补关系

| 机制 | 作用 | 互补点 |
|------|------|--------|
| **config.metadata** | LangChain 调用时传入，Langfuse Handler 可传播到子 Span | 子 LLM/工具调用自动带上 user_id、session_id、tags |
| **span.update_trace()** | 在 Trace 根节点设置属性，支持 invoke 后写 output | 可观测性更完整，支持按 output 分析 |

两者同时使用：`span.update_trace` 负责根 Trace 与 output，`config.metadata` 负责子 Span 的传播，形成完整链路。

---

## 七、总结

| 改造项 | 说明 |
|--------|------|
| **保留 RuntimeContext** | 工具依赖 `get_token_id()` 等，不可移除 |
| **增加 Langfuse Span** | 使用 `start_as_current_span`，支持 `update_trace` 设置属性及 output |
| **应用方案 A** | 在 `config["metadata"]` 中传入 `langfuse_user_id`、`langfuse_session_id`、`langfuse_tags` 等 |
| **嵌套顺序** | Langfuse Span（外）→ RuntimeContext（内）→ graph.ainvoke |
| **降级策略** | Langfuse 不可用时仅保留 RuntimeContext + graph.ainvoke |

---

## 八、完成情况

| 任务 | 状态 | 说明 |
|------|------|------|
| 步骤 1：确认 langfuse_handler 接口 | ✅ 已完成 | 从 `langfuse_handler` 直接导入 `get_langfuse_client`、`normalize_langfuse_trace_id` |
| 步骤 2：修改 chat.py | ✅ 已完成 | 已实现三层结构、config.metadata、嵌套逻辑、降级分支 |
| 步骤 3：验证 | ✅ 已完成 | 新增 `cursor_test/test_chat_extract_response_text.py`，7 个用例全部通过 |
| 提取逻辑重构 | ✅ 已完成 | 抽取 `_extract_response_text` 辅助函数，便于复用与测试 |

**改造文件**：
- `backend/app/api/routes/chat.py`：按 020207 方案完成改造
- `cursor_test/test_chat_extract_response_text.py`：新增 `_extract_response_text` 单元测试

**待人工验证**（需 Langfuse 启用环境）：
1. 工具调用时 `get_token_id()` 是否正常
2. Langfuse UI 中 Trace 是否具备 user_id、session_id、metadata、output
3. 按 session_id、user_id 筛选 Trace 是否生效
