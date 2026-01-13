# token_id 重构方案分析

## 一、问题背景

当前 `token_id` 的传递机制存在以下问题：

1. **依赖 contextvars**：使用 `TokenContext` 和 `contextvars` 传递 `token_id`，在 LangGraph 异步执行环境中可能存在上下文丢失风险
2. **信息不完整**：只传递了 `token_id`，但 `session_id`、`trace_id` 等运行时信息无法被工具获取
3. **状态数据未利用**：`initial_state` 中已经包含了完整的运行时数据，但工具无法直接访问

## 二、当前实现分析

### 2.1 当前数据流

```
ChatRequest (chat.py:30-33)
  ├─ token_id
  ├─ session_id
  ├─ trace_id
  └─ user_info
    ↓
build_initial_state (helpers.py:48-71)
  └─ FlowState {
      "token_id": request.token_id,
      "session_id": request.session_id,
      "trace_id": request.trace_id,
      ...
    }
    ↓
TokenContext(token_id=request.token_id) (chat.py:70)
  └─ contextvars.set(token_id)
    ↓
graph.invoke(initial_state, config) (chat.py:77)
  └─ LangGraph 异步执行
    ↓
TokenInjectedTool.ainvoke() (wrapper.py:179-222)
  └─ get_token_id() (context.py:24-31)
    └─ 从 contextvars 获取 token_id
      ↓
record_blood_pressure() (blood_pressure.py:47-55)
  └─ token_id 参数被注入
```

### 2.2 关键代码位置

#### 2.2.1 TokenContext 实现

```12:63:backend/domain/tools/context.py
# 创建上下文变量
_token_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'token_id', default=None
)

class TokenContext:
    """
    工具上下文管理器（上下文管理器协议）
    
    使用示例：
        with TokenContext(token_id="xxx"):
            # 在此上下文中，工具可以获取 token_id
            tool.invoke(...)
    """
    
    def __init__(self, token_id: str):
        self.token_id = token_id
        self._token = None
    
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

#### 2.2.2 TokenInjectedTool 实现

```70:112:backend/domain/tools/wrapper.py
def _inject_token_id(self, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    注入 tokenId 到工具参数中
    """
    # 从上下文获取 tokenId
    token_id = get_token_id()
    
    # 检查 tokenId 是否存在
    if token_id is None:
        if self._require_token:
            raise ValueError(
                f"工具 {self.name} 需要 tokenId，但上下文中未设置。"
                f"请确保在调用工具前使用 TokenContext 设置 tokenId。"
            )
        else:
            return tool_input
    
    # 注入 tokenId
    tool_input[self._token_id_param_name] = token_id
    return tool_input
```

#### 2.2.3 接口层使用

```70:77:backend/app/api/routes/chat.py
# 在TokenContext中执行流程图（确保工具可以获取token_id）
with TokenContext(token_id=request.token_id):
    # 构建配置（包含callbacks）
    config = {"configurable": {"thread_id": request.session_id}}
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
    
    # 执行流程图
    result = graph.invoke(initial_state, config)
```

## 三、问题分析

### 3.1 contextvars 在异步环境中的行为

**关键问题**：`contextvars` 在 Python 3.7+ 中支持异步上下文传递，但需要满足以下条件：

1. ✅ **同一事件循环**：如果所有异步任务在同一个事件循环中，`contextvars` 可以正确传递
2. ⚠️ **任务切换**：如果 LangGraph 内部创建了新的任务（`asyncio.create_task`），上下文应该能传递
3. ❌ **线程切换**：如果切换到其他线程，上下文会丢失

**当前代码的问题**：
- `with TokenContext()` 在同步代码中设置上下文
- `graph.invoke()` 是同步方法，但内部可能使用异步执行
- 如果 LangGraph 内部使用了线程池或进程池，`contextvars` 可能失效

### 3.2 with 语句的作用

```python
with TokenContext(token_id=request.token_id):
    result = graph.invoke(initial_state, config)
```

**with 语句的作用**：
- ✅ **语法有效**：`with` 语句是 Python 的上下文管理器协议，完全有效
- ✅ **上下文设置**：在 `__enter__` 中设置 `contextvars`
- ✅ **自动清理**：在 `__exit__` 中恢复之前的上下文
- ⚠️ **作用域限制**：只对当前同步代码块有效，对异步任务的影响取决于实现

**验证方法**：
- 在工具调用时打印 `get_token_id()` 的值
- 如果返回 `None`，说明上下文传递失败

### 3.3 状态数据访问问题

**当前状态结构**（`FlowState`）：

```9:26:backend/domain/state.py
class FlowState(TypedDict, total=False):
    """
    流程状态数据结构
    """
    current_message: HumanMessage
    history_messages: List[BaseMessage]
    flow_msgs: List[BaseMessage]
    session_id: str
    intent: Optional[str]
    token_id: Optional[str]  # 令牌ID（用于工具参数注入）
    trace_id: Optional[str]  # Trace ID（用于可观测性追踪）
    user_info: Optional[str]
    current_date: Optional[str]
```

**问题**：
- 状态中已经包含了 `token_id`、`session_id`、`trace_id`
- 但工具无法直接访问状态对象
- LangGraph 的工具调用机制不提供状态访问接口

## 四、可行方案分析

### 方案一：扩展 contextvars（推荐）

**原理**：扩展 `TokenContext` 支持更多字段，使用多个 `contextvars` 存储运行时信息。

**优点**：
- ✅ 最小改动，保持现有架构
- ✅ 支持异步上下文传递（Python 3.7+）
- ✅ 线程安全
- ✅ 可以传递多个字段（token_id、session_id、trace_id）

**缺点**：
- ⚠️ 需要验证在 LangGraph 异步环境中的有效性
- ⚠️ 如果 LangGraph 使用线程池，可能失效

**实现步骤**：

1. **扩展 context.py**：
```python
# 创建多个上下文变量
_token_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('token_id', default=None)
_session_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('session_id', default=None)
_trace_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('trace_id', default=None)

class RuntimeContext:
    """运行时上下文管理器（支持多个字段）"""
    
    def __init__(self, token_id: str = None, session_id: str = None, trace_id: str = None):
        self.token_id = token_id
        self.session_id = session_id
        self.trace_id = trace_id
        self._tokens = []
    
    def __enter__(self):
        """进入上下文"""
        if self.token_id:
            self._tokens.append(('token_id', _token_id_context.set(self.token_id)))
        if self.session_id:
            self._tokens.append(('session_id', _session_id_context.set(self.session_id)))
        if self.trace_id:
            self._tokens.append(('trace_id', _trace_id_context.set(self.trace_id)))
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        for name, token in reversed(self._tokens):
            if name == 'token_id':
                _token_id_context.reset(token)
            elif name == 'session_id':
                _session_id_context.reset(token)
            elif name == 'trace_id':
                _trace_id_context.reset(token)
        return False

def get_token_id() -> Optional[str]:
    return _token_id_context.get()

def get_session_id() -> Optional[str]:
    return _session_id_context.get()

def get_trace_id() -> Optional[str]:
    return _trace_id_context.get()
```

2. **修改 chat.py**：
```python
from backend.domain.tools.context import RuntimeContext

with RuntimeContext(
    token_id=request.token_id,
    session_id=request.session_id,
    trace_id=request.trace_id
):
    result = graph.invoke(initial_state, config)
```

3. **扩展 TokenInjectedTool**（可选）：
```python
# 如果需要注入 session_id 或 trace_id
def _inject_context(self, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    token_id = get_token_id()
    session_id = get_session_id()
    trace_id = get_trace_id()
    
    if token_id:
        tool_input['token_id'] = token_id
    if session_id:
        tool_input['session_id'] = session_id
    if trace_id:
        tool_input['trace_id'] = trace_id
    
    return tool_input
```

### 方案二：通过状态传递 + 节点注入

**原理**：在 LangGraph 节点中从状态提取数据，设置到 `contextvars`，然后调用工具。

**优点**：
- ✅ 不依赖 `with` 语句的作用域
- ✅ 在节点执行时主动设置上下文
- ✅ 可以访问完整的状态数据

**缺点**：
- ⚠️ 需要修改节点执行逻辑
- ⚠️ 需要在每个调用工具的节点中设置上下文

**实现步骤**：

1. **创建节点包装器**：
```python
def with_runtime_context(node_func):
    """节点包装器：在执行节点前设置运行时上下文"""
    async def wrapped_node(state: FlowState):
        # 从状态中提取运行时信息
        token_id = state.get('token_id')
        session_id = state.get('session_id')
        trace_id = state.get('trace_id')
        
        # 设置到 contextvars
        with RuntimeContext(
            token_id=token_id,
            session_id=session_id,
            trace_id=trace_id
        ):
            # 执行原始节点
            return await node_func(state)
    
    return wrapped_node
```

2. **在 Agent 节点中使用**：
```python
@with_runtime_context
async def agent_node(state: FlowState):
    # 工具调用时会自动从 contextvars 获取 token_id
    result = await agent_executor.invoke(state)
    return result
```

### 方案三：修改工具调用机制（不推荐）

**原理**：修改 LangGraph 的工具调用机制，让工具可以直接访问状态。

**优点**：
- ✅ 工具可以直接访问状态数据
- ✅ 不需要 contextvars

**缺点**：
- ❌ 需要深度修改 LangGraph 的内部机制
- ❌ 可能破坏 LangGraph 的封装
- ❌ 实现复杂度高，维护成本大

**结论**：不推荐此方案。

### 方案四：工具参数显式传递（不推荐）

**原理**：修改工具签名，让 LLM 显式传递 `token_id`、`session_id` 等参数。

**优点**：
- ✅ 简单直接
- ✅ 不需要上下文机制

**缺点**：
- ❌ LLM 可能忘记传递这些参数
- ❌ 增加了 LLM 的负担
- ❌ 不符合"自动注入"的设计理念

**结论**：不推荐此方案。

## 五、推荐方案：方案一（扩展 contextvars）

### 5.1 实施步骤

#### 步骤 1：扩展 context.py

```python
"""
工具上下文管理器
使用 contextvars 实现线程安全的运行时信息传递
"""
import contextvars
from typing import Optional

# 创建上下文变量
_token_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'token_id', default=None
)
_session_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'session_id', default=None
)
_trace_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'trace_id', default=None
)


def set_token_id(token_id: str) -> None:
    """设置当前上下文的 tokenId"""
    _token_id_context.set(token_id)


def get_token_id() -> Optional[str]:
    """获取当前上下文的 tokenId"""
    return _token_id_context.get()


def set_session_id(session_id: str) -> None:
    """设置当前上下文的 sessionId"""
    _session_id_context.set(session_id)


def get_session_id() -> Optional[str]:
    """获取当前上下文的 sessionId"""
    return _session_id_context.get()


def set_trace_id(trace_id: str) -> None:
    """设置当前上下文的 traceId"""
    _trace_id_context.set(trace_id)


def get_trace_id() -> Optional[str]:
    """获取当前上下文的 traceId"""
    return _trace_id_context.get()


class RuntimeContext:
    """
    运行时上下文管理器（支持多个字段）
    
    使用示例：
        with RuntimeContext(token_id="xxx", session_id="yyy", trace_id="zzz"):
            # 在此上下文中，工具可以获取所有运行时信息
            tool.invoke(...)
    """
    
    def __init__(
        self,
        token_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ):
        """
        初始化上下文管理器
        
        Args:
            token_id: 令牌ID
            session_id: 会话ID
            trace_id: 追踪ID
        """
        self.token_id = token_id
        self.session_id = session_id
        self.trace_id = trace_id
        self._tokens = []
    
    def __enter__(self):
        """进入上下文"""
        if self.token_id is not None:
            self._tokens.append(('token_id', _token_id_context.set(self.token_id)))
        if self.session_id is not None:
            self._tokens.append(('session_id', _session_id_context.set(self.session_id)))
        if self.trace_id is not None:
            self._tokens.append(('trace_id', _trace_id_context.set(self.trace_id)))
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，恢复之前的上下文"""
        for name, token in reversed(self._tokens):
            if name == 'token_id':
                _token_id_context.reset(token)
            elif name == 'session_id':
                _session_id_context.reset(token)
            elif name == 'trace_id':
                _trace_id_context.reset(token)
        return False


# 保持向后兼容
TokenContext = RuntimeContext
```

#### 步骤 2：修改 chat.py

```python
from backend.domain.tools.context import RuntimeContext

# 在RuntimeContext中执行流程图（确保工具可以获取运行时信息）
with RuntimeContext(
    token_id=request.token_id,
    session_id=request.session_id,
    trace_id=request.trace_id
):
    # 构建配置（包含callbacks）
    config = {"configurable": {"thread_id": request.session_id}}
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
    
    # 执行流程图
    result = graph.invoke(initial_state, config)
```

#### 步骤 3：工具中使用（可选）

如果工具需要 `session_id` 或 `trace_id`，可以这样获取：

```python
from backend.domain.tools.context import get_token_id, get_session_id, get_trace_id

@tool
async def record_blood_pressure(
    systolic: int,
    diastolic: int,
    heart_rate: Optional[int] = None,
    notes: Optional[str] = None,
    record_time: Optional[str] = None,
    token_id: str = ""  # 由TokenInjectedTool自动注入
) -> str:
    # 如果需要 session_id 或 trace_id，可以从上下文获取
    session_id = get_session_id()
    trace_id = get_trace_id()
    
    # 使用 token_id 进行业务逻辑
    # ...
```

### 5.2 验证方法

1. **添加日志验证**：
```python
# 在 TokenInjectedTool._inject_token_id 中添加
logger.info(
    f"[TokenInjectedTool] 上下文信息 - "
    f"token_id={get_token_id()}, "
    f"session_id={get_session_id()}, "
    f"trace_id={get_trace_id()}"
)
```

2. **测试用例**：
```python
async def test_runtime_context():
    """测试运行时上下文传递"""
    with RuntimeContext(token_id="test_token", session_id="test_session", trace_id="test_trace"):
        # 验证上下文设置
        assert get_token_id() == "test_token"
        assert get_session_id() == "test_session"
        assert get_trace_id() == "test_trace"
        
        # 模拟工具调用
        tool_input = {"systolic": 120, "diastolic": 80}
        injected = tool._inject_token_id(tool_input)
        assert injected["token_id"] == "test_token"
```

### 5.3 兼容性处理

为了保持向后兼容，可以保留 `TokenContext` 作为 `RuntimeContext` 的别名：

```python
# 向后兼容
TokenContext = RuntimeContext
```

这样现有代码不需要修改，但建议逐步迁移到 `RuntimeContext`。

## 六、方案对比

| 方案 | 实现复杂度 | 可靠性 | 可扩展性 | 推荐度 |
|------|-----------|--------|---------|--------|
| 方案一：扩展 contextvars | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 方案二：节点注入 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 方案三：修改工具机制 | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐ |
| 方案四：显式传递 | ⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ |

## 七、实施建议

### 7.1 短期方案（推荐）

**采用方案一：扩展 contextvars**

1. ✅ 最小改动，风险低
2. ✅ 保持现有架构
3. ✅ 支持多字段传递
4. ⚠️ 需要验证在 LangGraph 异步环境中的有效性

**实施步骤**：
1. 扩展 `context.py`，添加 `RuntimeContext` 和多字段支持
2. 修改 `chat.py`，使用 `RuntimeContext` 替代 `TokenContext`
3. 添加日志验证上下文传递
4. 测试工具调用是否正常获取 `token_id`

### 7.2 长期方案（备选）

如果方案一在异步环境中失效，可以考虑**方案二：节点注入**。

**实施步骤**：
1. 创建节点包装器 `with_runtime_context`
2. 在 Agent 节点中使用包装器
3. 从状态中提取运行时信息并设置到上下文

### 7.3 验证 checklist

- [ ] `contextvars` 在 LangGraph 异步环境中有效
- [ ] 工具可以正确获取 `token_id`
- [ ] 工具可以正确获取 `session_id`（如果需要）
- [ ] 工具可以正确获取 `trace_id`（如果需要）
- [ ] 多并发请求不会相互干扰
- [ ] 上下文在异常情况下能正确清理

## 八、总结

### 8.1 核心问题

1. **当前实现**：使用 `TokenContext` + `contextvars` 传递 `token_id`
2. **主要缺陷**：
   - 只支持 `token_id`，无法传递 `session_id`、`trace_id`
   - 在 LangGraph 异步环境中的有效性需要验证
3. **数据来源**：`initial_state` 中已包含完整运行时数据，但工具无法直接访问

### 8.2 推荐方案

**方案一：扩展 contextvars（RuntimeContext）**

- ✅ 最小改动，保持现有架构
- ✅ 支持多字段传递（token_id、session_id、trace_id）
- ✅ 线程安全，支持异步
- ⚠️ 需要验证在 LangGraph 中的有效性

### 8.3 实施优先级

1. **P0**：扩展 `context.py`，实现 `RuntimeContext`
2. **P0**：修改 `chat.py`，使用 `RuntimeContext`
3. **P1**：添加日志验证上下文传递
4. **P2**：工具中支持获取 `session_id`、`trace_id`（如果需要）

---

**文档生成时间**：2025-01-XX  
**代码版本**：V7.0  
**对应代码路径**：`/Users/m684620/work/github_GD25/gd25-biz-agent-python_cursor`

