# Langfuse 节点执行数据记录机制详解

## 文档说明

本文档详细解释在 `backend/app/api/routes/chat.py:73-74` 处获取的 `graph` 的每个节点在执行时，是如何调用 langfuse 记录数据的。

**文档版本**：V1.0  
**创建时间**：2025-01-XX

---

## 一、整体架构概览

### 1.1 数据记录流程

```
API 路由层 (chat.py)
    ↓
创建 Langfuse Trace 上下文
    ↓
获取编译后的 Graph
    ↓
执行 Graph (graph.invoke())
    ↓
节点执行 (Agent 节点)
    ↓
LLM 调用 (通过 Agent)
    ↓
Langfuse CallbackHandler 自动记录
    ↓
数据写入 Langfuse
```

### 1.2 关键组件

1. **Trace 上下文管理**：`langfuse_handler.py` - 管理 Trace 的创建和上下文传递
2. **LLM 客户端**：`llm/client.py` - 创建 LLM 实例时自动集成 Langfuse
3. **Agent 工厂**：`agents/factory.py` - 创建 Agent 时使用已集成 Langfuse 的 LLM
4. **图构建器**：`flows/builder.py` - 构建图时创建 Agent 节点

---

## 二、详细执行流程

### 2.1 第一步：API 路由层创建 Trace 上下文

在 `backend/app/api/routes/chat.py` 中：

```73:74:backend/app/api/routes/chat.py
        graph = FlowManager.get_flow(flow_name)
        
```

**执行前**（第 44-55 行）：

```44:55:backend/app/api/routes/chat.py
        langfuse_trace_id = set_langfuse_trace_context(
            # name="chat_request",
            name = request.flow_name or "UnknownChat",
            user_id=request.token_id,
            session_id=request.session_id,
            trace_id=trace_id,
            metadata={
                "message_length": len(request.message),
                "history_count": len(request.conversation_history) if request.conversation_history else 0,
                "flow_name": request.flow_name or "medical_agent",
            }
        )
```

**关键机制**：

1. **创建 Trace**：调用 `set_langfuse_trace_context()` 创建 Langfuse Trace
2. **建立上下文**：使用 `start_as_current_span()` 建立活动的 Span 上下文
3. **上下文变量**：将 Trace ID 存储到 `ContextVar` 中，供后续使用

**代码实现**（`langfuse_handler.py`）：

```60:87:backend/infrastructure/observability/langfuse_handler.py
    try:
        # 规范化 trace_id
        normalized_trace_id = normalize_langfuse_trace_id(trace_id)
        
        # 构建 trace 参数（参考 test_flow_trace.py 的实现方式）
        trace_params = {
            "name": name,
            "metadata": metadata or {},
        }
        
        # 如果提供了 trace_id，通过 trace_context 参数传入（参考 test_flow_trace.py 的做法）
        trace_params["trace_context"] = {"trace_id": normalized_trace_id}
        
        # 使用 start_as_current_span() 创建 Trace（参考 test_flow_trace.py 的正确调用方式）
        # 这会创建一个活动的 span 上下文，后续的所有 span 都会自动关联到这个 trace
        # 注意：start_as_current_span 使用 contextvars 管理上下文，即使不在 with 语句中也能保持活动状态
        langfuse_client.start_as_current_span(**trace_params).__enter__()
        
        # 在 Trace 上下文中，更新 trace 元数据（参考 test_flow_trace.py 的做法）
        langfuse_client.update_current_trace(
            name=name,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata or {},
        )
        
        # 将Trace ID存储到上下文变量中
        _trace_context.set(normalized_trace_id)
```

**重要说明**：
- `start_as_current_span()` 使用 Python 的 `contextvars` 机制管理上下文
- 即使不在 `with` 语句中，上下文也会在同一个异步上下文中保持活动状态
- 后续的所有 Langfuse 操作都会自动关联到这个 Trace

### 2.2 第二步：获取编译后的 Graph

```73:74:backend/app/api/routes/chat.py
        graph = FlowManager.get_flow(flow_name)
        
```

**执行流程**（`flows/manager.py`）：

```80:108:backend/domain/flows/manager.py
    @classmethod
    def get_flow(cls, flow_name: str) -> CompiledGraph:
        """
        获取流程图（按需加载）
        
        Args:
            flow_name: 流程名称
            
        Returns:
            CompiledGraph: 编译后的图
            
        Raises:
            ValueError: 流程不存在或加载失败
        """
        # 如果已编译，直接返回
        if flow_name in cls._compiled_graphs:
            return cls._compiled_graphs[flow_name]
        
        # 如果流程定义不存在，先扫描
        if flow_name not in cls._flow_definitions:
            cls.scan_flows()
        
        # 如果仍然不存在，报错
        if flow_name not in cls._flow_definitions:
            raise ValueError(f"流程定义不存在: {flow_name}")
        
        # 加载并编译流程
        cls._load_and_compile_flow(flow_name)
        
        return cls._compiled_graphs[flow_name]
```

**关键点**：
- Graph 在编译时已经绑定了所有节点函数
- 节点函数中已经创建了 Agent 实例
- Agent 实例中已经创建了 LLM 实例（此时 LLM 已集成 Langfuse）

### 2.3 第三步：执行 Graph

```128:128:backend/app/api/routes/chat.py
            result = graph.invoke(initial_state, config)
```

**执行机制**：
- LangGraph 会按照图的定义顺序执行各个节点
- 每个节点执行时，会调用对应的节点函数
- 节点函数执行完成后，状态会自动保存（通过 Checkpointer）

### 2.4 第四步：节点执行（Agent 节点）

**节点函数创建**（`flows/builder.py`）：

```88:165:backend/domain/flows/builder.py
    @staticmethod
    def _create_node_function(node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
        创建节点函数
        
        Args:
            node_def: 节点定义
            flow_def: 流程定义
            
        Returns:
            Callable: 节点函数
        """
        if node_def.type == "agent":
            # Agent节点
            from backend.domain.flows.definition import AgentNodeConfig, ModelConfig
            
            # 解析节点配置
            config_dict = node_def.config
            model_config = ModelConfig(**config_dict["model"])
            agent_config = AgentNodeConfig(
                prompt=config_dict["prompt"],
                model=model_config,
                tools=config_dict.get("tools")
            )
            
            # 创建Agent
            agent_executor = AgentFactory.create_agent(
                config=agent_config,
                flow_dir=flow_def.flow_dir or ""
            )
            
            # 创建节点函数
            # 捕获节点名称，用于意图识别节点的特殊处理
            node_name = node_def.name
            
            def agent_node(state: FlowState) -> FlowState:
                """Agent节点函数"""
                # 获取最后一条用户消息
                if not state.get("messages"):
                    return state
                
                last_message = state["messages"][-1]
                input_text = last_message.content if hasattr(last_message, "content") else str(last_message)
                
                # 执行Agent
                result = agent_executor.invoke({
                    "input": input_text
                })
                
                # 更新状态
                new_state = state.copy()
                if "output" in result:
                    # AgentExecutor返回output字段
                    output = result["output"]
                    # 如果是意图识别节点，解析JSON并更新intent
                    if node_name == "intent_recognition":
                        import json
                        try:
                            # 尝试从输出中提取JSON
                            if isinstance(output, str):
                                # 查找JSON部分
                                json_start = output.find("{")
                                json_end = output.rfind("}") + 1
                                if json_start >= 0 and json_end > json_start:
                                    json_str = output[json_start:json_end]
                                    intent_data = json.loads(json_str)
                                    new_state["intent"] = intent_data.get("intent", "unclear")
                        except Exception as e:
                            logger.warning(f"解析意图识别结果失败: {e}")
                            new_state["intent"] = "unclear"
                    
                    # 将输出添加到消息列表
                    from langchain_core.messages import AIMessage
                    new_state["messages"] = state["messages"] + [AIMessage(content=output)]
                
                return new_state
            
            return agent_node
```

**关键点**：
- 节点函数在**图编译时**创建（不是执行时）
- Agent 实例在**节点函数创建时**创建（图编译时）
- LLM 实例在**Agent 创建时**创建（图编译时）

### 2.5 第五步：Agent 执行（调用 LLM）

**Agent 创建**（`agents/factory.py`）：

```74:128:backend/domain/agents/factory.py
    @staticmethod
    def create_agent(
        config: AgentNodeConfig,
        flow_dir: str,
        tools: Optional[List[BaseTool]] = None
    ) -> AgentExecutor:
        """
        创建Agent实例（使用LangGraph的create_react_agent）
        
        Args:
            config: Agent节点配置
            flow_dir: 流程目录路径（用于解析提示词相对路径）
            tools: 工具列表（可选）
            
        Returns:
            AgentExecutor: Agent执行器
        """
        # 加载提示词
        prompt_content = prompt_manager.get_prompt(
            prompt_path=config.prompt,
            flow_dir=flow_dir
        )
        
        # 获取工具列表
        agent_tools = []
        if config.tools:
            for tool_name in config.tools:
                tool = tool_registry.get_tool(tool_name)
                if tool:
                    agent_tools.append(tool)
                else:
                    logger.warning(f"工具 {tool_name} 未注册，跳过")
        
        if tools:
            agent_tools.extend(tools)
        
        # 使用TokenInjectedTool包装所有工具（自动注入token_id）
        agent_tools = wrap_tools_with_token_context(agent_tools)
        
        # 创建LLM客户端
        llm = get_llm(
            provider=config.model.provider,
            model=config.model.name,
            temperature=config.model.temperature
        )
        
        # 使用LangGraph的create_react_agent创建图
        graph = create_react_agent(
            model=llm,
            tools=agent_tools,
            prompt=prompt_content  # 直接传入提示词字符串
        )
        
        logger.debug(f"创建Agent: {config.prompt}, 工具数量: {len(agent_tools)}")
        return AgentExecutor(graph, agent_tools, verbose=True)
```

**关键点**：
- Agent 创建时调用 `get_llm()` 创建 LLM 实例
- LLM 实例在创建时自动集成 Langfuse CallbackHandler

### 2.6 第六步：LLM 创建时自动集成 Langfuse

**LLM 创建**（`llm/client.py`）：

```20:97:backend/infrastructure/llm/client.py
def get_llm(
    provider: str,
    model: str,
    temperature: Optional[float] = None,
    callbacks: Optional[List[BaseCallbackHandler]] = None,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 客户端实例
    
    Args:
        provider: 模型供应商名称（如 "doubao", "openai", "deepseek"）
        model: 模型名称（如 "doubao-seed-1-6-251015"）
        temperature: 温度参数，默认使用配置中的温度
        callbacks: 回调处理器列表（可选，如果未提供则自动添加Langfuse回调）
        **kwargs: 其他参数（可以覆盖默认的 api_key 和 base_url）
        
    Returns:
        BaseChatModel: LLM 客户端实例
        
    Raises:
        RuntimeError: 如果供应商配置未加载
        ValueError: 如果供应商不存在或配置无效
    """
    # 获取供应商配置
    provider_config = ProviderManager.get_provider(provider)
    if provider_config is None:
        raise ValueError(f"模型供应商 '{provider}' 未注册，请检查配置文件")
    
    # 使用传入的参数或供应商配置
    api_key = kwargs.get("api_key", provider_config.api_key)
    base_url = kwargs.get("base_url", provider_config.base_url)
    
    # 温度参数
    if temperature is None:
        temperature = settings.LLM_TEMPERATURE
    
    # 准备回调处理器列表
    callback_list = list(callbacks) if callbacks else []
    
    # 自动添加Langfuse回调处理器（如果可用且未手动提供）
    if not callbacks:
        langfuse_handler = create_langfuse_handler(
            context={
                "provider": provider,
                "model": model,
                "temperature": temperature,
            }
        )
        if langfuse_handler:
            callback_list.append(langfuse_handler)
            logger.info(
                f"[Langfuse] 自动添加CallbackHandler: provider={provider}, "
                f"model={model}, callbacks_count={len(callback_list)}"
            )
        else:
            logger.debug(
                f"[Langfuse] CallbackHandler不可用，跳过: provider={provider}, model={model}"
            )
    
    # 创建 LLM 客户端
    # 注意：所有供应商都使用 ChatOpenAI，因为它们都兼容 OpenAI API 格式
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=api_key,
        openai_api_base=base_url,
        callbacks=callback_list if callback_list else None,
        **{k: v for k, v in kwargs.items() if k not in ["api_key", "base_url"]}
    )
    
    logger.debug(
        f"创建 LLM 客户端: provider={provider}, model={model}, "
        f"temperature={temperature}, base_url={base_url}, "
        f"callbacks_count={len(callback_list)}"
    )
    
    return llm
```

**关键机制**：

1. **自动添加 CallbackHandler**：如果未手动提供 callbacks，会自动创建 `LangfuseCallbackHandler`
2. **关联 Trace**：CallbackHandler 会自动关联到当前活动的 Trace（通过 contextvars）
3. **自动记录**：每次 LLM 调用时，CallbackHandler 会自动记录到 Langfuse

**CallbackHandler 创建**（`langfuse_handler.py`）：

```112:173:backend/infrastructure/observability/langfuse_handler.py
def create_langfuse_handler(
    context: Optional[Dict[str, Any]] = None
) -> Optional["LangfuseCallbackHandler"]:
    """
    创建Langfuse CallbackHandler
    
    用于在LLM调用时自动记录到Langfuse。
    
    Args:
        context: 上下文信息（可选，用于记录元数据）
                如果包含 trace_id 键，将用于关联到已存在的 Trace
        
    Returns:
        LangfuseCallbackHandler: Langfuse回调处理器，如果Langfuse未启用或配置不完整则返回None
        
    Raises:
        ValueError: Langfuse未启用或配置不完整
    """
    # 检查是否启用（从统一配置读取）
    if not settings.LANGFUSE_ENABLED:
        logger.debug("[Langfuse] CallbackHandler: Langfuse未启用")
        return None
    
    # 从统一配置读取
    public_key = settings.LANGFUSE_PUBLIC_KEY
    secret_key = settings.LANGFUSE_SECRET_KEY
    
    if not public_key or not secret_key:
        logger.warning(
            "[Langfuse] CallbackHandler: 配置不完整，缺少PUBLIC_KEY或SECRET_KEY。"
            "请检查.env文件配置。"
        )
        return None
    
    # 确保全局 Langfuse 客户端已初始化（用于 secret_key 和 host 配置）
    # langfuse 3.x 的 CallbackHandler 会使用全局客户端配置
    _get_langfuse_client()
    
    # 构建 trace_context（用于分布式追踪）
    trace_context = None
    if context and isinstance(context, dict) and context.get("trace_id"):
        trace_context = {"trace_id": context.get("trace_id")}
    
    try:
        # 创建 Langfuse Callback Handler
        # 注意：langfuse.langchain.CallbackHandler 只需要 public_key，不需要 secret_key
        # secret_key 通过全局客户端配置传递
        handler = LangfuseCallbackHandler(
            public_key=public_key,
            update_trace=True,  # 更新 trace 信息
            trace_context=trace_context,  # 关联到已存在的 trace
        )
        
        logger.debug(
            f"[Langfuse] CallbackHandler创建成功: "
            f"trace_context={trace_context}, context={context}"
        )
        return handler
    
    except Exception as e:
        logger.error(f"[Langfuse] CallbackHandler创建失败: {e}", exc_info=True)
        return None
```

**重要说明**：
- `LangfuseCallbackHandler` 会自动检测当前活动的 Trace（通过 contextvars）
- 即使不传入 `trace_context`，也会自动关联到已存在的 Trace
- `update_trace=True` 确保会更新 Trace 信息

### 2.7 第七步：LLM 调用时自动记录

**执行流程**：

1. **Agent 执行**：Agent 节点函数调用 `agent_executor.invoke()`
2. **LLM 调用**：Agent 内部调用 LLM（通过 LangGraph 的 `create_react_agent`）
3. **Callback 触发**：LLM 调用时，LangChain 会自动触发所有注册的 CallbackHandler
4. **数据记录**：`LangfuseCallbackHandler` 自动记录以下信息：
   - **Span**：每次 LLM 调用创建一个 Span
   - **Generation**：记录 LLM 的输入和输出
   - **Token 使用**：记录 token 消耗
   - **延迟**：记录调用延迟
   - **元数据**：记录模型、温度等参数

**自动关联机制**：

- **Trace 关联**：通过 `contextvars` 自动关联到当前活动的 Trace
- **Span 层级**：每次 LLM 调用创建一个子 Span，自动成为 Trace 的子节点
- **元数据继承**：自动继承 Trace 的 user_id、session_id 等元数据

---

## 三、关键技术点

### 3.1 ContextVars 机制

**工作原理**：

1. **Trace 创建时**：使用 `start_as_current_span()` 建立上下文
2. **上下文传递**：Python 的 `contextvars` 在同一个异步上下文中自动传递
3. **自动关联**：后续的所有 Langfuse 操作都会自动关联到这个 Trace

**代码实现**：

```python
# langfuse_handler.py
from contextvars import ContextVar

# 全局上下文变量
_trace_context: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)

# 设置 Trace 上下文
langfuse_client.start_as_current_span(**trace_params).__enter__()
_trace_context.set(normalized_trace_id)
```

### 3.2 CallbackHandler 自动关联

**工作原理**：

1. **创建时**：CallbackHandler 创建时不需要显式传入 Trace ID
2. **运行时**：CallbackHandler 运行时自动检测当前活动的 Trace
3. **记录时**：记录数据时自动关联到当前 Trace

**Langfuse SDK 实现**：

- Langfuse SDK 内部使用 `contextvars` 管理 Trace 上下文
- `LangfuseCallbackHandler` 会自动从上下文获取当前 Trace
- 每次 LLM 调用时，自动创建 Span 并关联到 Trace

### 3.3 执行时机

**关键时机**：

1. **图编译时**（应用启动或首次加载流程）：
   - 创建节点函数
   - 创建 Agent 实例
   - 创建 LLM 实例（此时集成 Langfuse CallbackHandler）

2. **API 请求时**：
   - 创建 Trace 上下文
   - 执行 Graph（调用节点函数）
   - 节点函数调用 Agent
   - Agent 调用 LLM
   - CallbackHandler 自动记录

**重要说明**：

- LLM 实例在**图编译时**创建，不是每次请求时创建
- 但 CallbackHandler 会在**每次 LLM 调用时**自动关联到当前活动的 Trace
- 这意味着同一个 LLM 实例可以在不同的 Trace 中记录数据

---

## 四、数据记录内容

### 4.1 Trace 级别

- **Trace ID**：唯一标识一次完整的对话流程
- **Name**：流程名称（如 "medical_agent"）
- **User ID**：用户 ID（token_id）
- **Session ID**：会话 ID
- **Metadata**：自定义元数据（消息长度、历史记录数等）

### 4.2 Span 级别（每次 LLM 调用）

- **Span ID**：唯一标识一次 LLM 调用
- **Name**：Span 名称（通常是模型名称）
- **Input**：LLM 的输入（提示词 + 消息）
- **Output**：LLM 的输出（生成的文本）
- **Model**：使用的模型名称
- **Temperature**：温度参数
- **Token 使用**：输入 token 数、输出 token 数、总 token 数
- **延迟**：调用延迟（毫秒）
- **Metadata**：其他元数据

### 4.3 层级关系

```
Trace (一次对话流程)
  ├─ Span 1 (第一次 LLM 调用)
  │   ├─ Generation (输入/输出)
  │   └─ Token 使用
  ├─ Span 2 (第二次 LLM 调用)
  │   ├─ Generation (输入/输出)
  │   └─ Token 使用
  └─ ...
```

---

## 五、总结

### 5.1 核心机制

1. **Trace 创建**：在 API 路由层创建 Trace，建立上下文
2. **自动集成**：LLM 创建时自动集成 Langfuse CallbackHandler
3. **自动关联**：CallbackHandler 自动关联到当前活动的 Trace
4. **自动记录**：每次 LLM 调用时自动记录到 Langfuse

### 5.2 关键优势

1. **零侵入**：节点代码不需要显式调用 Langfuse API
2. **自动关联**：通过 contextvars 自动关联 Trace
3. **完整记录**：自动记录所有 LLM 调用的详细信息
4. **性能优化**：LLM 实例复用，但 Trace 隔离

### 5.3 注意事项

1. **上下文传递**：确保在同一个异步上下文中执行
2. **Trace 创建时机**：必须在执行 Graph 之前创建 Trace
3. **配置检查**：确保 Langfuse 配置正确（ENABLED、PUBLIC_KEY、SECRET_KEY）

---

**文档生成时间**：2025-01-XX  
**代码版本**：V2.0  
**对应代码路径**：`/Users/m684620/work/github_GD25/gd25-biz-agent-python_cursor`

