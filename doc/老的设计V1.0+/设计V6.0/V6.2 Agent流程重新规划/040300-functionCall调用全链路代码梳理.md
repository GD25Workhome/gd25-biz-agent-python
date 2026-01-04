# Function Call 调用全链路代码梳理

## 一、概述

本文档梳理了当模型回调返回类型为 `function_call`（在 LangChain 中对应 `tool_calls`）时的完整代码调用链路。包括从 API 入口到工具执行，再到结果返回的全过程。

**关键概念**：
- **Function Call**：LLM 返回的工具调用请求（OpenAI 格式中称为 `function_call`）
- **Tool Calls**：LangChain 中的工具调用格式（对应 `AIMessage.tool_calls`）
- **Tool Message**：工具执行结果返回的消息格式（`ToolMessage`）

## 二、调用链路总览

```
1. API 入口 (app/api/routes.py)
   ↓
2. 路由图执行 (domain/router/graph.py)
   ↓
3. Agent 节点执行 (domain/router/graph.py:with_user_context)
   ↓
4. LangChain Agent 内部执行 (langchain.agents.create_agent)
   ↓
5. LLM 调用 (infrastructure/llm/client.py)
   ↓
6. LLM 响应处理 (返回 AIMessage，可能包含 tool_calls)
   ↓
7. 工具调用执行 (LangChain Agent 自动处理)
   ↓
8. 工具包装器 (domain/tools/wrapper.py:TokenInjectedTool)
   ↓
9. 实际工具执行 (domain/tools/*/record.py 等)
   ↓
10. 工具结果返回 (ToolMessage)
   ↓
11. Agent 继续执行 (基于工具结果生成最终回复)
   ↓
12. 结果返回给 API (提取 AIMessage.content)
```

## 三、详细代码链路分析

### 3.1 API 入口层

**文件位置**：`app/api/routes.py`

**关键代码**：

```24:130:app/api/routes.py
@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    app_request: Request,
    x_trace_id: Optional[str] = Header(None, alias="X-Trace-ID")
) -> ChatResponse:
    # ... 初始化逻辑 ...
    
    # 构建初始状态
    initial_state: RouterState = {
        "messages": messages,
        "current_intent": None,
        "current_agent": None,
        "need_reroute": True,
        "session_id": request.session_id,
        "token_id": request.token_id,
        "trace_id": trace_id,
        # ...
    }
    
    # 执行路由图
    async for event in router_graph.astream(initial_state, config=config):
        for node_name, node_output in event.items():
            result = node_output
```

**职责**：
1. 接收 HTTP 请求，构建初始状态
2. 调用路由图的 `astream` 方法执行
3. 收集执行结果，提取最终回复

**关键数据流转**：
- 输入：`ChatRequest`（包含 `token_id`、`session_id`、`message` 等）
- 状态：`RouterState`（包含 `messages`、`token_id`、`session_id` 等）
- 输出：`ChatResponse`（包含 `response`、`intent`、`agent` 等）

---

### 3.2 路由图执行层

**文件位置**：`domain/router/graph.py`

**关键代码**：

```80:241:domain/router/graph.py
def with_user_context(agent_node, agent_name: str):
    async def _run(state: RouterState) -> RouterState:
        messages = state.get("messages", [])
        token_id = state.get("token_id")
        session_id = state.get("session_id")
        
        # ... 系统消息处理 ...
        
        # 在 TokenContext 中调用 Agent
        with TokenContext(token_id=token_id):
            result = await agent_node.ainvoke({"messages": messages_with_context})
        
        # 返回结果
        return result
```

**职责**：
1. 准备系统消息（包含占位符填充）
2. 设置 `TokenContext`，供工具自动注入 `token_id`
3. 调用 Agent 节点执行
4. 处理执行结果

**关键实现点**：
- **TokenContext 设置**：使用 `with TokenContext(token_id=token_id)` 设置上下文，工具包装器可以自动获取 `token_id`
- **系统消息注入**：在消息列表开头插入系统消息，包含完整的上下文信息

---

### 3.3 Agent 创建层

**文件位置**：`domain/agents/factory.py`

**关键代码**：

```87:217:domain/agents/factory.py
@classmethod
def create_agent(
    cls,
    agent_key: str,
    llm: Optional[BaseChatModel] = None,
    tools: Optional[List[BaseTool]] = None,
    force_reload: bool = False
):
    # ... 缓存检查 ...
    
    # 获取工具列表
    if not tools:
        tool_names = agent_config.get("tools", [])
        tools = [
            TOOL_REGISTRY[name]
            for name in tool_names
            if name in TOOL_REGISTRY
        ]
    
    # 包装工具，使其支持自动注入 tokenId
    tools = wrap_tools_with_token_context(
        tools,
        token_id_param_name="token_id",
        require_token=True
    )
    
    # 创建 ReAct Agent
    return create_agent(
        model=llm,
        tools=tools,
        # 不传入 prompt 参数，避免 create_agent 自动添加系统消息
    )
```

**职责**：
1. 从配置加载工具列表
2. 包装工具（通过 `wrap_tools_with_token_context`），使其支持自动注入 `token_id`
3. 创建 LangChain ReAct Agent

**关键实现点**：
- **工具包装**：所有工具都通过 `TokenInjectedTool` 包装，确保在调用时自动注入 `token_id`
- **Agent 创建**：使用 LangChain 的 `create_agent`，它会自动处理工具调用逻辑

---

### 3.4 LLM 调用层

**文件位置**：`infrastructure/llm/client.py`

**关键代码**：

```29:118:infrastructure/llm/client.py
def get_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    log_context: Optional[LlmLogContext] = None,
    enable_logging: Optional[bool] = None,
    enable_langfuse: Optional[bool] = None,
    **kwargs
) -> BaseChatModel:
    # ... 参数处理 ...
    
    # 添加 Langfuse Callback（如果启用）
    if langfuse_enabled:
        langfuse_handler = create_langfuse_handler(log_context)
        callbacks.append(langfuse_handler)
    
    # 添加日志回调处理器
    callbacks.append(
        LlmLogCallbackHandler(
            context=log_context,
            model=model or settings.LLM_MODEL,
            # ...
        )
    )
    
    # 创建 LLM 客户端
    return ChatOpenAI(**params)
```

**职责**：
1. 创建 LLM 客户端实例（`ChatOpenAI`）
2. 配置回调处理器（Langfuse、日志记录等）
3. 返回 LLM 实例供 Agent 使用

**关键实现点**：
- **回调处理器**：自动添加 Langfuse 和日志回调，记录所有 LLM 调用
- **LLM 实例**：使用 `ChatOpenAI`，兼容 OpenAI API 格式

---

### 3.5 LangChain Agent 内部执行（自动处理工具调用）

**框架层**：`langchain.agents.create_agent`

**执行流程**（LangChain 内部实现，简化说明）：

1. **接收消息**：从 `RouterState` 获取 `messages` 列表
2. **LLM 推理**：
   - 将消息和工具定义发送给 LLM
   - LLM 分析用户意图，决定是否需要调用工具
   - 如果决定调用工具，LLM 返回 `AIMessage`，其中包含 `tool_calls` 属性
3. **检测工具调用**：
   - 检查 `AIMessage.tool_calls` 是否存在且不为空
   - 如果存在，提取工具调用信息（工具名称、参数、`tool_call_id`）
4. **执行工具**：
   - 对于每个 `tool_call`，调用对应的工具
   - 将工具结果包装成 `ToolMessage`，关联 `tool_call_id`
5. **继续执行**：
   - 将 `ToolMessage` 添加到消息列表
   - 再次调用 LLM（包含工具结果）
   - LLM 基于工具结果生成最终回复
6. **返回结果**：
   - 更新 `RouterState`，包含所有消息（包括工具调用和最终回复）

**关键数据结构**：

```python
# LLM 返回的 AIMessage（包含工具调用）
AIMessage(
    content="...",
    tool_calls=[
        {
            "id": "call_xxx",  # tool_call_id
            "name": "record_blood_pressure",  # 工具名称
            "args": {
                "systolic": 120,
                "diastolic": 80,
                # ...
            }
        }
    ]
)

# 工具执行结果
ToolMessage(
    content="成功记录血压：...",
    tool_call_id="call_xxx",  # 关联到对应的 tool_call
    name="record_blood_pressure"
)
```

---

### 3.6 工具包装器层

**文件位置**：`domain/tools/wrapper.py`

**关键代码**：

```15:356:domain/tools/wrapper.py
class TokenInjectedTool(BaseTool):
    """工具包装器：在工具调用时自动注入 tokenId"""
    
    def __init__(
        self,
        tool: BaseTool,
        token_id_param_name: str = "token_id",
        require_token: bool = True
    ):
        # ... 初始化 ...
        self._original_tool = tool
        self._token_id_param_name = token_id_param_name
        self._require_token = require_token
    
    def _inject_token_id(self, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """注入 tokenId 到工具参数中"""
        # 从上下文获取 tokenId
        token_id = get_token_id()
        
        # 注入 tokenId
        tool_input[token_id_param_name] = token_id
        return tool_input
    
    async def ainvoke(
        self,
        tool_input: Any,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
        **kwargs: Any
    ) -> Any:
        """异步调用工具（自动注入 tokenId）"""
        # 处理不同的 tool_input 格式
        if isinstance(tool_input, dict):
            # 检查是否是 LangChain 工具调用格式（包含 'args' 字段）
            if 'args' in tool_input and isinstance(tool_input.get('args'), dict):
                args_dict = tool_input['args'].copy()
                injected_args = self._inject_token_id(args_dict)
                injected_input = injected_args
            else:
                # 直接参数字典格式
                injected_input = self._inject_token_id(tool_input.copy())
        
        # 调用原始工具
        result = await original_tool.ainvoke(injected_input, run_manager=run_manager, **kwargs)
        
        # 如果结果是字符串，且 tool_input 包含 'id' 字段，包装成 ToolMessage
        if isinstance(result, str) and isinstance(tool_input, dict) and 'id' in tool_input:
            tool_call_id = tool_input.get('id', '')
            tool_message = ToolMessage(
                content=result,
                tool_call_id=tool_call_id,
                name=tool_name
            )
            return tool_message
        
        return result
```

**职责**：
1. 包装原始工具，拦截工具调用
2. 从 `TokenContext` 获取 `token_id`
3. 自动将 `token_id` 注入到工具参数中
4. 调用原始工具
5. 处理返回值（可能需要包装成 `ToolMessage`）

**关键实现点**：
- **上下文获取**：通过 `get_token_id()` 从 `contextvars` 获取当前上下文的 `token_id`
- **参数注入**：自动将 `token_id` 添加到工具参数字典中
- **格式处理**：支持两种格式的工具调用：
  - LangChain 格式：`{'name': '...', 'args': {...}, 'id': '...'}`
  - 直接参数字典：`{'systolic': 120, 'diastolic': 80, ...}`
- **返回值包装**：如果工具返回字符串且需要关联 `tool_call_id`，自动包装成 `ToolMessage`

**上下文管理器**：

```1:63:domain/tools/context.py
# 工具上下文管理器
class TokenContext:
    """使用 contextvars 实现线程安全的 tokenId 传递"""
    
    def __enter__(self):
        """进入上下文"""
        self._token = _token_id_context.set(self.token_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，恢复之前的上下文"""
        if self._token is not None:
            _token_id_context.reset(self._token)
        return False
```

**工作原理**：
- 使用 Python 的 `contextvars` 模块实现线程安全的上下文变量
- 在 Agent 节点执行前设置 `token_id`（通过 `with TokenContext(token_id=token_id)`）
- 工具包装器在调用时通过 `get_token_id()` 获取当前上下文的 `token_id`

---

### 3.7 实际工具执行层

**文件位置**：`domain/tools/blood_pressure/record.py`（以血压记录工具为例）

**关键代码**：

```49:174:domain/tools/blood_pressure/record.py
@tool(args_schema=RecordBloodPressureInput)
async def record_blood_pressure(
    systolic: int,
    diastolic: int,
    heart_rate: Optional[int] = None,
    record_time: Optional[str] = None,
    notes: Optional[str] = None,
    token_id: str = ""  # 由系统自动注入
) -> str:
    """记录血压数据到数据库"""
    
    # 验证 token_id
    if not token_id or token_id == "":
        return f"错误：token_id 参数缺失或为空"
    
    # 转换 token_id 为用户信息
    user_info = convert_token_to_user_info(token_id)
    user_id = user_info.user_id
    
    # 获取数据库会话
    session_factory = get_async_session_factory()
    session = session_factory()
    
    try:
        # 创建记录
        repo = BloodPressureRepository(session)
        record = await repo.create(
            user_id=user_id,
            systolic=systolic,
            diastolic=diastolic,
            heart_rate=heart_rate,
            notes=notes,
            record_time=record_datetime
        )
        
        # 提交事务
        await session.commit()
        
        # 返回成功消息
        return f"成功记录血压：收缩压 {systolic} mmHg，舒张压 {diastolic} mmHg"
    except Exception as e:
        await session.rollback()
        raise
    finally:
        await session.close()
```

**职责**：
1. 接收工具参数（包括自动注入的 `token_id`）
2. 验证参数（确保 `token_id` 存在）
3. 转换 `token_id` 为用户信息（通过 `convert_token_to_user_info`）
4. 执行业务逻辑（如数据库操作）
5. 返回结果字符串

**关键实现点**：
- **参数接收**：工具函数签名中包含 `token_id` 参数，由工具包装器自动注入
- **参数验证**：检查 `token_id` 是否存在，如果缺失则返回错误
- **业务逻辑**：执行实际的业务操作（如数据库写入）
- **返回值**：返回字符串，由 LangChain Agent 包装成 `ToolMessage`

---

### 3.8 工具结果处理与 Agent 继续执行

**框架层**：LangChain Agent 自动处理

**执行流程**：

1. **工具结果接收**：
   - 工具执行完成后，返回字符串结果
   - 工具包装器（或 LangChain）将结果包装成 `ToolMessage`
   - `ToolMessage` 包含：
     - `content`：工具返回的字符串结果
     - `tool_call_id`：关联到对应的 `tool_call.id`
     - `name`：工具名称

2. **消息列表更新**：
   - 将 `ToolMessage` 添加到消息列表
   - 消息列表现在包含：
     - `HumanMessage`（用户消息）
     - `AIMessage`（包含 `tool_calls`）
     - `ToolMessage`（工具执行结果）

3. **LLM 再次调用**：
   - Agent 将包含工具结果的消息列表发送给 LLM
   - LLM 基于工具结果生成最终回复
   - LLM 返回新的 `AIMessage`（通常不再包含 `tool_calls`）

4. **结果返回**：
   - 更新 `RouterState`，包含完整的消息列表
   - 返回给路由图

**关键代码**（在 `domain/router/graph.py` 中）：

```243:329:domain/router/graph.py
# 检查返回结果中的消息，追踪工具调用情况
result_messages = result.get("messages", [])

# 分析消息类型，查找工具调用
tool_calls = []
for msg in result_messages:
    if isinstance(msg, ToolMessage):
        tool_calls.append({
            "tool_call_id": getattr(msg, "tool_call_id", "N/A"),
            "name": getattr(msg, "name", "N/A"),
            "content_preview": str(msg.content)[:200]
        })
    elif isinstance(msg, AIMessage):
        # 检查AI消息中是否包含工具调用
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_calls.append({
                    "tool_call_id": getattr(tool_call, "id", "N/A"),
                    "name": getattr(tool_call, "name", "N/A"),
                    "args_preview": str(getattr(tool_call, "args", {}))[:200]
                })
```

---

### 3.9 结果提取与返回

**文件位置**：`app/api/routes.py`

**关键代码**：

```145:181:app/api/routes.py
# 获取最后一条助手消息
response_message = None
for msg in reversed(result.get("messages", [])):
    if isinstance(msg, AIMessage):
        response_message = msg
        break

if not response_message:
    response_message = "抱歉，我无法理解您的问题。"
else:
    response_message = response_message.content

# 获取意图和智能体信息
intent = result.get("current_intent")
agent = result.get("current_agent")

# 返回响应
return ChatResponse(
    response=response_message,
    session_id=request.session_id,
    intent=intent,
    agent=agent
)
```

**职责**：
1. 从执行结果中提取最后一条 `AIMessage`
2. 获取 `AIMessage.content` 作为最终回复
3. 提取意图和智能体信息
4. 返回 `ChatResponse`

**关键实现点**：
- **消息提取**：从后往前遍历消息列表，找到最后一条 `AIMessage`
- **内容提取**：获取 `AIMessage.content`（这是 LLM 基于工具结果生成的最终回复）
- **响应构建**：构建 `ChatResponse`，包含回复、意图、智能体等信息

---

## 四、关键数据流转

### 4.1 请求阶段

```
ChatRequest
  ↓
RouterState {
    messages: [HumanMessage(...)],
    token_id: "...",
    session_id: "...",
    ...
}
  ↓
Agent 节点执行
  ↓
Agent 内部状态 {
    messages: [
        SystemMessage(...),
        HumanMessage(...)
    ]
}
```

### 4.2 工具调用阶段

```
LLM 响应
  ↓
AIMessage {
    content: "...",
    tool_calls: [{
        id: "call_xxx",
        name: "record_blood_pressure",
        args: {
            systolic: 120,
            diastolic: 80
        }
    }]
}
  ↓
LangChain Agent 检测到 tool_calls
  ↓
工具调用（通过 TokenInjectedTool）
  ↓
_inject_token_id() {
    args: {
        systolic: 120,
        diastolic: 80,
        token_id: "xxx"  // 自动注入
    }
}
  ↓
实际工具执行
  ↓
ToolMessage {
    content: "成功记录血压：...",
    tool_call_id: "call_xxx",
    name: "record_blood_pressure"
}
```

### 4.3 结果生成阶段

```
消息列表更新
  ↓
[
    SystemMessage(...),
    HumanMessage(...),
    AIMessage(..., tool_calls=[...]),  // LLM 的工具调用请求
    ToolMessage(...)  // 工具执行结果
]
  ↓
LLM 再次调用（包含工具结果）
  ↓
AIMessage {
    content: "已成功记录您的血压数据：收缩压 120 mmHg，舒张压 80 mmHg"
}
  ↓
RouterState 更新
  ↓
ChatResponse {
    response: "已成功记录您的血压数据：...",
    intent: "blood_pressure",
    agent: "blood_pressure_agent"
}
```

---

## 五、关键实现点总结

### 5.1 工具自动注入 token_id

**实现方式**：
1. 使用 `contextvars` 实现线程安全的上下文变量
2. 在 Agent 节点执行前设置 `TokenContext(token_id=token_id)`
3. 工具包装器 `TokenInjectedTool` 自动从上下文获取 `token_id` 并注入

**关键代码位置**：
- 上下文设置：`domain/router/graph.py:212`（`with TokenContext(token_id=token_id)`）
- 上下文获取：`domain/tools/context.py:24`（`get_token_id()`）
- 参数注入：`domain/tools/wrapper.py:61`（`_inject_token_id()`）

### 5.2 工具调用格式处理

**支持的格式**：
1. **LangChain 工具调用格式**：
   ```python
   {
       'name': 'record_blood_pressure',
       'args': {
           'systolic': 120,
           'diastolic': 80
       },
       'id': 'call_xxx',
       'type': 'tool_call'
   }
   ```
2. **直接参数字典格式**：
   ```python
   {
       'systolic': 120,
       'diastolic': 80
   }
   ```

**处理逻辑**：在 `TokenInjectedTool.ainvoke()` 中检测格式并分别处理

### 5.3 工具结果包装

**处理逻辑**：
- 如果工具返回字符串，且 `tool_input` 包含 `id` 字段，自动包装成 `ToolMessage`
- 确保 `ToolMessage.tool_call_id` 与对应的 `tool_call.id` 匹配

**关键代码位置**：`domain/tools/wrapper.py:245`（`ainvoke()` 方法）

### 5.4 工具调用日志记录

**实现方式**：
- 在 `domain/router/graph.py` 中记录工具调用的详细信息
- 记录工具调用数量、工具名称、参数预览等

**关键代码位置**：`domain/router/graph.py:243-329`

---

## 六、常见问题与注意事项

### 6.1 token_id 缺失问题

**问题**：工具调用时 `token_id` 为空或缺失

**原因**：
- 未在 Agent 节点执行前设置 `TokenContext`
- 上下文变量被意外重置

**解决方案**：
- 确保在调用 Agent 节点前使用 `with TokenContext(token_id=token_id)`
- 检查工具包装器的 `require_token` 参数设置

### 6.2 工具调用格式不匹配

**问题**：工具包装器无法正确解析工具调用格式

**原因**：
- LangChain 版本更新导致格式变化
- 工具调用格式与预期不符

**解决方案**：
- 检查 `TokenInjectedTool.ainvoke()` 中的格式检测逻辑
- 添加日志记录，输出实际的 `tool_input` 格式

### 6.3 工具结果未正确关联

**问题**：`ToolMessage` 的 `tool_call_id` 与 `tool_call.id` 不匹配

**原因**：
- 工具包装器未正确传递 `tool_call_id`
- 工具返回结果时未关联 `tool_call_id`

**解决方案**：
- 确保 `ToolMessage` 的 `tool_call_id` 与对应的 `tool_call.id` 一致
- 检查工具包装器的返回值包装逻辑

### 6.4 多轮工具调用处理

**问题**：Agent 需要调用多个工具时，如何确保所有工具都能正确执行

**说明**：
- LangChain Agent 支持在一条 `AIMessage` 中包含多个 `tool_calls`
- 所有工具调用会并行执行（如果支持）
- 所有工具结果会添加到消息列表，供 LLM 生成最终回复

---

## 七、相关代码文件索引

### 7.1 核心文件

| 文件路径 | 职责 | 关键类/函数 |
|---------|------|------------|
| `app/api/routes.py` | API 入口 | `chat()` |
| `domain/router/graph.py` | 路由图构建与执行 | `create_router_graph()`, `with_user_context()` |
| `domain/agents/factory.py` | Agent 创建 | `AgentFactory.create_agent()` |
| `domain/tools/wrapper.py` | 工具包装器 | `TokenInjectedTool`, `wrap_tools_with_token_context()` |
| `domain/tools/context.py` | 上下文管理 | `TokenContext`, `get_token_id()` |
| `infrastructure/llm/client.py` | LLM 客户端 | `get_llm()` |
| `domain/tools/blood_pressure/record.py` | 工具实现示例 | `record_blood_pressure()` |

### 7.2 配置文件

| 文件路径 | 职责 |
|---------|------|
| `config/agents.yaml` | Agent 配置（工具列表、LLM 设置等） |

### 7.3 框架层

| 框架/库 | 职责 |
|---------|------|
| `langchain.agents.create_agent` | 创建 ReAct Agent，自动处理工具调用 |
| `langchain_core.messages` | 消息类型定义（`AIMessage`, `ToolMessage` 等） |
| `contextvars` | 线程安全的上下文变量 |

---

## 八、调试与排查建议

### 8.1 启用详细日志

在关键位置添加日志记录：
1. **Agent 节点执行前**：记录 `token_id`、消息列表
2. **工具调用时**：记录 `tool_input` 格式、注入后的参数
3. **工具执行后**：记录返回结果、是否包装成 `ToolMessage`
4. **LLM 响应时**：记录 `tool_calls` 信息

### 8.2 检查点清单

- [ ] `TokenContext` 是否在 Agent 节点执行前设置
- [ ] 工具是否正确包装（`TokenInjectedTool`）
- [ ] 工具参数是否包含 `token_id`
- [ ] `ToolMessage` 的 `tool_call_id` 是否正确关联
- [ ] 消息列表是否包含完整的调用链（`HumanMessage` → `AIMessage(tool_calls)` → `ToolMessage` → `AIMessage`）

### 8.3 测试建议

1. **单工具调用测试**：测试单个工具调用是否正常工作
2. **多工具调用测试**：测试 Agent 在一次响应中调用多个工具
3. **token_id 注入测试**：验证 `token_id` 是否正确注入
4. **工具结果处理测试**：验证工具结果是否正确返回给 LLM

---

## 九、总结

Function Call 调用链路涉及多个层次和组件，核心流程如下：

1. **API 入口**：接收请求，构建初始状态
2. **路由图执行**：路由到对应的 Agent 节点
3. **Agent 执行**：调用 LangChain Agent，可能触发工具调用
4. **工具调用**：通过工具包装器自动注入 `token_id`，执行实际工具
5. **结果返回**：工具结果返回给 Agent，Agent 生成最终回复
6. **响应提取**：从执行结果中提取最终回复，返回给用户

关键实现点：
- 使用 `contextvars` 实现线程安全的 `token_id` 传递
- 工具包装器自动注入 `token_id`，简化工具实现
- LangChain Agent 自动处理工具调用流程，无需手动管理

整个链路实现了从用户请求到工具执行再到结果返回的完整闭环。

