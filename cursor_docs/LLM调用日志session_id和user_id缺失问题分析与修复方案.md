# LLM调用日志 session_id 和 user_id 缺失问题分析与修复方案

## 一、问题分析

### 1.1 问题描述

在 `biz_agent_llm_call_logs` 表中，部分记录的 `session_id` 和 `user_id` 字段为空（NULL），导致无法通过日志追踪具体的用户会话和请求链路。

### 1.2 问题根因

通过代码分析，发现以下问题：

1. **LLM 日志记录机制已实现**：
   - `infrastructure/observability/llm_logger.py` 中的 `LlmLogCallbackHandler` 已经支持通过 `LlmLogContext` 传递上下文信息
   - `LlmLogContext` 包含 `session_id`、`user_id`、`agent_key`、`trace_id` 等字段

2. **但调用 `get_llm` 时未传入上下文**：
   - `domain/router/tools/router_tools.py` 中的 `identify_intent` 和 `clarify_intent` 工具调用 `get_llm()` 时未传入 `log_context` 参数
   - `domain/agents/factory.py` 中的 `AgentFactory.create_agent()` 调用 `get_llm()` 时也未传入 `log_context` 参数

3. **上下文信息存在于 RouterState**：
   - `RouterState` 中包含 `session_id` 和 `user_id`
   - 但在工具层和工厂层调用时，无法直接访问 RouterState

### 1.3 调用链路分析

```
用户请求 (app/api/routes.py)
  └─> RouterState (包含 session_id, user_id)
       └─> route_node / agent_node
            └─> identify_intent / clarify_intent (tools)
                 └─> get_llm() ❌ 未传入 log_context
            └─> AgentFactory.create_agent()
                 └─> get_llm() ❌ 未传入 log_context
```

## 二、修复方案

### 2.1 方案概述

采用**上下文传递**的方式，从 RouterState 中提取 `session_id` 和 `user_id`，并通过调用链传递到 `get_llm()` 函数。

### 2.2 具体修复点

#### 修复点 1: router_tools.py - 传递上下文给工具

**问题**：`identify_intent` 和 `clarify_intent` 是 LangChain 的 `@tool` 装饰的工具函数，无法直接接收额外的状态信息。

**方案**：修改工具函数，使其能够从调用上下文中获取 RouterState 信息。

**实现方式**：
- 方案 A（推荐）：通过工具的 `config` 参数传递上下文信息
- 方案 B：修改工具签名，增加可选的上下文参数

#### 修复点 2: AgentFactory.create_agent() - 传递上下文

**问题**：`AgentFactory.create_agent()` 无法直接访问 RouterState。

**方案**：在调用 `create_agent()` 的地方（`graph.py` 的 `with_user_context` 包装器）传入上下文信息。

**实现方式**：
- 修改 `create_agent()` 方法，增加 `log_context` 参数
- 在 `graph.py` 中调用时传入从 RouterState 提取的上下文

#### 修复点 3: 工具调用时的上下文传递

**问题**：在 `route_node` 和 `clarify_intent_node` 中调用工具时，需要传递上下文信息。

**方案**：通过工具的运行时配置（`config`）传递上下文，工具函数从配置中读取。

## 三、详细实现方案

### 3.1 修改 router_tools.py

**目标**：让 `identify_intent` 和 `clarify_intent` 能够从上下文获取 session_id 和 user_id。

**实现**：使用 LangChain 的运行时配置机制（run_manager.config）传递上下文。

```python
# 在 identify_intent 函数中
@tool
def identify_intent(messages: list[BaseMessage], config: Optional[Dict] = None) -> Dict[str, Any]:
    # 从 config 中获取上下文
    run_manager = config.get("run_manager") if config else None
    if run_manager and run_manager.parent_run_id:
        # 尝试从父运行上下文中获取状态
        pass
    
    # 或者通过修改工具调用方式传递上下文
    # 需要在调用时传入额外的上下文参数
```

**更简单的方案**：修改工具函数签名，增加可选的上下文参数，然后在调用时传入。

```python
@tool
def identify_intent(
    messages: list[BaseMessage],
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    agent_key: Optional[str] = None
) -> Dict[str, Any]:
    # 构建日志上下文
    log_context = LlmLogContext(
        session_id=session_id,
        user_id=user_id,
        agent_key=agent_key or "router_tools"
    )
    
    # 调用LLM时传入上下文
    llm = get_llm(
        temperature=settings.LLM_TEMPERATURE_INTENT,
        log_context=log_context
    )
    # ... 其他代码
```

### 3.2 修改 AgentFactory.create_agent()

```python
@classmethod
def create_agent(
    cls,
    agent_key: str,
    llm: Optional[BaseChatModel] = None,
    tools: Optional[List[BaseTool]] = None,
    log_context: Optional[LlmLogContext] = None  # 新增参数
):
    # ... 现有代码
    
    if not llm:
        llm_config = agent_config.get("llm", {})
        llm = get_llm(
            model=llm_config.get("model", settings.LLM_MODEL),
            temperature=llm_config.get(
                "temperature",
                settings.LLM_TEMPERATURE_DEFAULT
            ),
            log_context=log_context  # 传入上下文
        )
```

### 3.3 修改 graph.py 中的 with_user_context

```python
def with_user_context(agent_node, agent_name: str):
    async def _run(state: RouterState) -> RouterState:
        messages = state.get("messages", [])
        user_id = state.get("user_id")
        session_id = state.get("session_id")  # 获取 session_id
        
        # 构建日志上下文
        from infrastructure.observability.llm_logger import LlmLogContext
        log_context = LlmLogContext(
            session_id=session_id,
            user_id=user_id,
            agent_key=agent_name
        )
        
        # 创建智能体时传入上下文
        agent = AgentFactory.create_agent(
            agent_key=agent_name,
            log_context=log_context
        )
        # ... 其他代码
```

### 3.4 修改 node.py 中的工具调用

```python
def route_node(state: RouterState) -> RouterState:
    messages = state.get("messages", [])
    session_id = state.get("session_id")
    user_id = state.get("user_id")
    
    # 识别意图时传入上下文
    intent_result_dict = identify_intent.invoke({
        "messages": messages,
        "session_id": session_id,
        "user_id": user_id,
        "agent_key": "router_tools"
    })
    # ... 其他代码

def clarify_intent_node(state: RouterState) -> RouterState:
    messages = state.get("messages", [])
    session_id = state.get("session_id")
    user_id = state.get("user_id")
    last_message = messages[-1]
    user_query = last_message.content if hasattr(last_message, 'content') else str(last_message)
    
    # 调用澄清工具时传入上下文
    clarification = clarify_intent.invoke({
        "query": user_query,
        "session_id": session_id,
        "user_id": user_id,
        "agent_key": "router_tools"
    })
    # ... 其他代码
```

## 四、实施步骤

1. **修改 router_tools.py**
   - 修改 `identify_intent` 工具函数签名，增加上下文参数
   - 修改 `clarify_intent` 工具函数签名，增加上下文参数
   - 在函数内部构建 `LlmLogContext` 并传给 `get_llm()`

2. **修改 AgentFactory.create_agent()**
   - 增加 `log_context` 参数
   - 在创建 LLM 时传入上下文

3. **修改 graph.py**
   - 在 `with_user_context` 中从 RouterState 提取上下文
   - 创建智能体时传入上下文

4. **修改 node.py**
   - 在 `route_node` 中调用工具时传入上下文参数
   - 在 `clarify_intent_node` 中调用工具时传入上下文参数

5. **测试验证**
   - 创建测试用例，验证日志记录中包含 session_id 和 user_id
   - 检查数据库中记录的完整性

## 五、注意事项

1. **向后兼容**：新增的参数应该设为可选（`Optional`），避免破坏现有调用
2. **工具签名兼容**：LangChain 工具函数的参数变更需要确保不影响工具注册和使用
3. **错误处理**：如果上下文信息缺失，应该记录警告但不影响主流程
4. **性能影响**：传递上下文信息对性能影响很小，主要是参数传递的开销

## 六、预期效果

修复后，所有 LLM 调用日志都应该包含：
- `session_id`: 会话ID，用于追踪同一会话的所有LLM调用
- `user_id`: 用户ID，用于关联特定用户的调用记录
- `agent_key`: 智能体标识，用于区分不同智能体的调用

这样可以实现：
- ✅ 完整的请求链路追踪
- ✅ 按用户/会话查询和分析调用记录
- ✅ 更好的问题定位和审计能力
