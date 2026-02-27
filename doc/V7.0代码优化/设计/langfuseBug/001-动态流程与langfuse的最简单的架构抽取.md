# 动态流程与Langfuse的最简单的架构抽取

## 文档目的

本文档抽取了动态流程执行和Langfuse日志记录的核心架构，用于构建简单的测试场景，实验和修复Langfuse动态流程记录日志的问题。

---

## 一、核心架构概览

### 1.1 数据流转图

```
API请求层
  ↓ 设置Trace上下文
[set_langfuse_trace_context] 
  ↓ 创建Trace，设置ContextVar
动态流程执行层
  ↓ 获取流程图
[FlowManager.get_flow]
  ↓ 构建图（编译时）
[GraphBuilder.build_graph]
  ↓ 创建节点函数（编译时）
  ↓ 节点执行（运行时）
[agent_node函数] 
  ↓ 从ContextVar获取trace_id
  ↓ 创建Langfuse Handler（运行时）
[create_langfuse_handler]
  ↓ LLM调用时自动记录
[LLM invoke with callbacks]
```

### 1.2 关键时间点

- **编译时**：图构建、节点函数创建
- **运行时**：Trace上下文设置、节点执行、Handler创建、LLM调用

---

## 二、核心组件抽取

### 2.1 Langfuse Trace上下文设置（API层）

**位置**：`backend/infrastructure/observability/langfuse_handler.py`

**核心函数**：`set_langfuse_trace_context()`

**关键逻辑**：
1. 创建Trace（使用 `start_as_current_span()`）
2. 设置ContextVar存储trace_id
3. 更新Trace元数据

```python
def set_langfuse_trace_context(
    name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """设置Langfuse Trace上下文"""
    
    # 1. 规范化trace_id
    normalized_trace_id = normalize_langfuse_trace_id(trace_id)
    
    # 2. 创建Trace（最外层的span就是trace）
    langfuse_client.start_as_current_span(
        name=name,
        trace_context={"trace_id": normalized_trace_id},
        metadata=metadata or {}
    ).__enter__()
    
    # 3. 更新Trace元数据
    langfuse_client.update_current_trace(
        name=name,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata or {}
    )
    
    # 4. 存储trace_id到ContextVar（关键！）
    _trace_context.set(normalized_trace_id)
    
    return normalized_trace_id
```

**关键点**：
- 使用 `start_as_current_span()` 创建Trace（最外层的span就是trace）
- 通过 `ContextVar` 存储trace_id，供后续节点使用
- 使用 `trace_context` 参数关联已存在的Trace

---

### 2.2 Langfuse Handler创建

**位置**：`backend/infrastructure/observability/langfuse_handler.py`

**核心函数**：`create_langfuse_handler()`

**关键逻辑**：
1. 尝试从context参数或ContextVar获取trace_id
2. 构建trace_context（如果获取到trace_id）
3. 创建LangfuseCallbackHandler

```python
def create_langfuse_handler(
    context: Optional[Dict[str, Any]] = None
) -> Optional["LangfuseCallbackHandler"]:
    """创建Langfuse CallbackHandler"""
    
    trace_id = None
    
    # 1. 优先从context参数获取trace_id
    if context and context.get("trace_id"):
        trace_id = context.get("trace_id")
    
    # 2. 如果未获取到，从ContextVar获取
    if not trace_id:
        trace_id = get_current_trace_id()
    
    # 3. 构建trace_context（如果获取到trace_id）
    trace_context = None
    if trace_id:
        normalized_trace_id = normalize_langfuse_trace_id(trace_id)
        trace_context = {"trace_id": normalized_trace_id}
    # 注意：如果trace_id为None，不设置trace_context
    # LangfuseCallbackHandler会自动检测当前活动的trace
    
    # 4. 创建Handler
    handler = LangfuseCallbackHandler(
        public_key=public_key,
        update_trace=True,
        trace_context=trace_context,  # 关联到已存在的Trace
    )
    
    return handler
```

**关键点**：
- 优先从context参数获取trace_id
- 其次从ContextVar获取trace_id
- 如果都获取不到，不设置trace_context，让Handler自动检测当前活动的trace

---

### 2.3 动态流程节点函数创建（编译时）

**位置**：`backend/domain/flows/builder.py`

**核心函数**：`GraphBuilder._create_node_function()`

**关键逻辑**：
1. 创建Agent（编译时）
2. 创建节点函数（编译时捕获Agent）
3. 节点函数内部在运行时获取trace_id和创建Handler

```python
@staticmethod
def _create_node_function(node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
    """创建节点函数"""
    
    if node_def.type == "agent":
        # 1. 创建Agent（编译时）
        agent_executor = AgentFactory.create_agent(
            config=agent_config,
            flow_dir=flow_def.flow_dir or ""
        )
        
        # 2. 创建节点函数（编译时）
        def agent_node(state: FlowState) -> FlowState:
            """Agent节点函数（运行时执行）"""
            
            # 3. 运行时：从ContextVar获取trace_id
            trace_id = get_current_trace_id()
            
            # 4. 运行时：创建Langfuse Handler
            callbacks = []
            if trace_id:
                langfuse_handler = create_langfuse_handler()
                if langfuse_handler:
                    callbacks.append(langfuse_handler)
            
            # 5. 运行时：执行Agent，传递callbacks
            result = agent_executor.invoke(
                {"input": input_text},
                callbacks=callbacks if callbacks else None
            )
            
            return new_state
        
        return agent_node
```

**关键点**：
- Agent在**编译时**创建（图构建时）
- 节点函数在**编译时**创建，但Handler在**运行时**创建
- 节点执行时从ContextVar获取trace_id，创建Handler
- Handler传递给Agent的invoke方法

---

### 2.4 流程执行入口

**位置**：`backend/app/api/routes/chat.py`

**核心逻辑**：
1. 设置Trace上下文
2. 获取流程图
3. 执行流程图

```python
@router.post("/chat")
async def chat(request: ChatRequest, app_request: Request) -> ChatResponse:
    """聊天接口"""
    
    # 1. 设置Langfuse Trace上下文（关键！）
    trace_id = request.trace_id or secrets.token_hex(16)
    set_langfuse_trace_context(
        name=request.flow_name or "UnknownChat",
        user_id=request.token_id,
        session_id=request.session_id,
        trace_id=trace_id,
        metadata={...}
    )
    
    # 2. 获取流程图（按需加载）
    flow_name = request.flow_name or "medical_agent"
    graph = FlowManager.get_flow(flow_name)
    
    # 3. 构建初始状态
    initial_state: FlowState = {
        "messages": messages,
        "session_id": request.session_id,
        ...
    }
    
    # 4. 执行流程图
    config = {"configurable": {"thread_id": request.session_id}}
    result = graph.invoke(initial_state, config)
    
    return ChatResponse(...)
```

**关键点**：
- 必须在执行流程图**之前**设置Trace上下文
- Trace上下文通过ContextVar传递到节点函数中

---

## 三、关键问题和测试点

### 3.1 ContextVar传递问题

**问题**：ContextVar在异步环境中的传递是否正常？

**测试点**：
1. ContextVar是否能在节点函数中正确获取？
2. 多线程/多协程环境下的ContextVar隔离是否正确？

### 3.2 Handler创建时机问题

**问题**：Handler应该在什么时候创建？

**当前方案**：
- 编译时创建Agent（不包含Handler）
- 运行时在节点函数中创建Handler

**可能的替代方案**：
1. 编译时创建Handler（但trace_id未知）
2. 在API层创建Handler并传递（需要修改Agent调用方式）
3. 运行时动态创建Handler（当前方案）

### 3.3 Trace关联问题

**问题**：LLM调用是否能正确关联到Trace？

**测试点**：
1. Handler的trace_context是否正确设置？
2. 如果trace_context为None，Handler能否自动关联到当前活动的Trace？
3. 多个节点执行时，是否都能正确关联到同一个Trace？

---

## 四、简化测试架构

### 4.1 最小化测试场景

**测试场景**：单节点流程 + 单次LLM调用

```
API请求
  ↓
设置Trace上下文
  ↓
执行单节点流程
  ↓
节点函数：创建Handler → 调用LLM
  ↓
验证Trace是否正确记录
```

### 4.2 测试代码结构

```python
# 测试代码示例结构
def test_minimal_flow():
    # 1. 设置Trace上下文
    trace_id = "test_trace_001"
    set_langfuse_trace_context(
        name="test_flow",
        trace_id=trace_id
    )
    
    # 2. 创建最小化流程（单节点）
    graph = create_minimal_graph()
    
    # 3. 执行流程
    initial_state = {"messages": [HumanMessage("Hello")]}
    result = graph.invoke(initial_state)
    
    # 4. 验证Trace记录
    # ... 验证逻辑
```

---

## 五、可能的问题和解决方案

### 5.1 问题1：ContextVar在异步环境中丢失

**现象**：节点函数中无法获取trace_id

**可能原因**：
- ContextVar在异步上下文切换时丢失
- LangGraph的内部执行机制导致ContextVar隔离

**测试方法**：
```python
def agent_node(state: FlowState) -> FlowState:
    trace_id = get_current_trace_id()
    logger.info(f"[TEST] trace_id in node: {trace_id}")
    # ... 其他逻辑
```

### 5.2 问题2：Handler无法关联到Trace

**现象**：LLM调用记录在新的Trace中，而不是现有的Trace

**可能原因**：
- trace_context参数未正确传递
- Langfuse SDK的contextvars机制失效

**测试方法**：
```python
# 在创建Handler时记录trace_context
handler = create_langfuse_handler()
logger.info(f"[TEST] handler trace_context: {handler.trace_context}")
```

### 5.3 问题3：多节点执行时Trace分散

**现象**：每个节点执行时创建了新的Trace

**可能原因**：
- 每个节点都创建了新的Handler，且未正确关联
- ContextVar在节点之间丢失

**测试方法**：
```python
# 在每个节点执行前后记录trace_id
def agent_node(state: FlowState) -> FlowState:
    trace_id_before = get_current_trace_id()
    logger.info(f"[TEST] trace_id before: {trace_id_before}")
    
    # ... 执行逻辑
    
    trace_id_after = get_current_trace_id()
    logger.info(f"[TEST] trace_id after: {trace_id_after}")
```

---

## 六、实验代码建议

### 6.1 实验目录结构

```
cursor_test/
  langfuse/
    minimal/
      test_minimal_flow.py       # 最小化流程测试
      test_contextvar.py          # ContextVar传递测试
      test_handler_creation.py    # Handler创建测试
      test_trace_association.py   # Trace关联测试
```

### 6.2 实验步骤

1. **步骤1**：测试ContextVar传递
   - 创建最简单的节点函数
   - 验证能否获取trace_id

2. **步骤2**：测试Handler创建
   - 在节点函数中创建Handler
   - 验证trace_context是否正确

3. **步骤3**：测试LLM调用记录
   - 调用LLM并传递Handler
   - 验证是否记录到正确的Trace

4. **步骤4**：测试多节点流程
   - 创建多节点流程
   - 验证所有节点是否关联到同一个Trace

---

## 七、参考代码位置

### 7.1 核心文件

- `backend/infrastructure/observability/langfuse_handler.py`
  - `set_langfuse_trace_context()` - 设置Trace上下文
  - `create_langfuse_handler()` - 创建Handler
  - `get_current_trace_id()` - 获取当前trace_id

- `backend/domain/flows/builder.py`
  - `GraphBuilder._create_node_function()` - 创建节点函数
  - 节点函数内部的Handler创建逻辑

- `backend/app/api/routes/chat.py`
  - `chat()` - API入口，设置Trace上下文

### 7.2 相关配置

- `backend/app/config.py` - Langfuse配置
- `backend/infrastructure/llm/client.py` - LLM客户端封装

---

## 八、下一步行动

1. **创建最小化测试场景**
   - 单节点流程
   - 单次LLM调用
   - 验证Trace记录

2. **逐步增加复杂度**
   - 多节点流程
   - 多次LLM调用
   - 工具调用

3. **定位问题**
   - 通过日志定位问题点
   - 尝试不同的埋点方式
   - 验证哪种方式有效

4. **修复问题**
   - 修复发现的问题
   - 更新生产代码
   - 更新本文档

---

**文档生成时间**：2025-01-06  
**目的**：用于实验和修复Langfuse动态流程记录日志问题

