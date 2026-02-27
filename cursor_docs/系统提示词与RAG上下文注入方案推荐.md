# 系统提示词与 RAG 上下文注入方案推荐

## 📋 需求分析

### 当前实现

1. **系统提示词**：在 `config/flows/*/prompts/*.txt` 中，编译时加载
2. **对话历史**：运行时通过 `messages` 字段传入（已实现）
3. **当前消息**：运行时通过 `messages` 字段传入（已实现）

### 新增需求

1. **患者信息**：从缓存接口获取，需要在运行时注入到 SystemMessage
2. **医学参考资料**：RAG 检索结果，需要在运行时注入到 SystemMessage
3. **系统提示词**：评估是否应该改为运行时注入

---

## 🎯 推荐方案：混合方案（编译时 + 运行时）

### 方案概述

**核心思路**：
- ✅ **基础系统提示词**（静态部分）：编译时加载，放在配置文件
- ✅ **动态上下文**（患者信息、RAG资料）：运行时注入，合并到 SystemMessage
- ✅ **对话历史**：运行时通过 `messages` 传入（当前实现已正确）

### 方案架构

```
编译阶段（Agent 创建时）：
  ├─ 加载基础系统提示词（config/flows/*/prompts/*.txt）
  └─ 创建 Agent（不绑定 prompt，或使用占位符）

运行时（节点执行时）：
  ├─ 获取基础系统提示词
  ├─ 获取患者信息（从缓存接口）
  ├─ 获取 RAG 资料（检索医学参考资料）
  ├─ 合并为完整 SystemMessage
  └─ 构建消息列表：SystemMessage + 历史消息 + 当前消息
```

---

## 📝 详细方案说明

### 1. 系统提示词管理：编译时 + 运行时混合

#### ✅ 推荐：保持编译时加载基础提示词 + 运行时注入动态内容

**原因**：
1. ✅ **性能优势**：基础提示词（如角色定义、规则）在编译时加载，避免每次请求重复加载
2. ✅ **灵活性**：动态内容（患者信息、RAG）在运行时注入，可以根据每个请求定制
3. ✅ **分离关注点**：静态配置与动态数据分离，代码更清晰
4. ✅ **缓存友好**：基础提示词可以缓存，动态内容实时获取

#### ❌ 不推荐：完全运行时加载

**原因**：
1. ❌ 每次请求都要读取文件，性能较差
2. ❌ 无法利用 LangGraph 的编译时优化
3. ❌ 代码复杂度增加（需要处理文件读取、错误处理等）

### 2. 对话历史和当前消息：运行时注入（当前实现正确）

**当前实现**（`backend/app/api/routes/chat.py`）：

```75:85:backend/app/api/routes/chat.py
        # 构建消息列表（从conversation_history和当前消息）
        messages = []
        if request.conversation_history:
            for msg in request.conversation_history:
                if msg.role == "user":
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    messages.append(AIMessage(content=msg.content))
        
        # 添加当前用户消息
        messages.append(HumanMessage(content=request.message))
```

**✅ 这是正确的**，继续使用这种方式。

### 3. RAG 上下文注入：运行时注入到 SystemMessage

**推荐方式**：将患者信息和医学参考资料合并到 SystemMessage 中

**原因**：
1. ✅ **语义清晰**：这些是上下文信息，不是对话历史
2. ✅ **模型理解**：LLM 能更好地区分系统指令和上下文数据
3. ✅ **Token 效率**：放在 SystemMessage 中，模型知道这是参考信息
4. ✅ **灵活性**：可以根据请求动态调整内容

---

## 🔧 具体实现方案

### 方案一：修改节点函数，在运行时构建完整 SystemMessage（推荐）

**实现思路**：
1. Agent 创建时，保存基础提示词（而不是直接传给 `create_react_agent`）
2. 节点执行时，动态构建包含完整上下文的 SystemMessage
3. 手动调用 LLM（不依赖 `create_react_agent` 的 prompt 参数）

**代码示例**：

```python
# backend/domain/agents/factory.py (修改)
class AgentExecutor:
    def __init__(self, graph: Any, tools: List[BaseTool], base_prompt: str, llm: BaseChatModel, verbose: bool = False):
        """
        初始化Agent执行器
        
        Args:
            graph: LangGraph编译后的图（可选，如果使用手动调用方式）
            tools: 工具列表
            base_prompt: 基础系统提示词（用于运行时合并）
            llm: LLM客户端
            verbose: 是否输出详细信息
        """
        self.graph = graph  # 可选
        self.tools = tools
        self.base_prompt = base_prompt  # 保存基础提示词
        self.llm = llm
        self.verbose = verbose

# backend/domain/flows/builder.py (修改节点函数)
def agent_node_action(state: FlowState) -> FlowState:
    """Agent节点函数（支持运行时注入动态上下文）"""
    from langchain_core.messages import SystemMessage, HumanMessage
    
    # 1. 获取基础系统提示词
    base_prompt = agent_executor.base_prompt
    
    # 2. 获取患者信息（从缓存接口）
    patient_info = get_patient_info(state.get("token_id"))
    # 示例：{"name": "张三", "age": 35, "history": "高血压病史"}
    
    # 3. 获取 RAG 资料（医学参考资料）
    rag_context = retrieve_medical_references(state.get("messages", [])[-1].content)
    # 示例：根据用户问题检索相关医学资料
    
    # 4. 合并为完整系统提示词
    full_system_prompt = f"""{base_prompt}

患者信息：
{format_patient_info(patient_info)}

医学参考资料：
{rag_context}
"""
    
    # 5. 构建完整消息列表
    messages = [
        SystemMessage(content=full_system_prompt),
        *state.get("messages", [])  # 包含历史消息和当前消息
    ]
    
    # 6. 调用 LLM（手动调用，使用 create_react_agent 的工具绑定逻辑）
    # 注意：这里需要使用工具绑定的 LLM，或者使用 create_react_agent 的图
    # 如果使用 create_react_agent，需要修改其实现方式
    
    # 方案A：使用 create_react_agent 但通过状态传递系统消息
    # 方案B：手动调用 LLM + 工具调用逻辑
    
    # 这里提供方案A的思路（需要修改 AgentFactory 实现）：
    # 1. create_react_agent 不传入 prompt，使用空 prompt 或占位符
    # 2. 在节点函数中，动态构建消息列表（包含完整 SystemMessage）
    # 3. 调用 AgentExecutor，传入完整消息列表
    
    return new_state
```

**挑战**：
- `create_react_agent` 会将 `prompt` 参数转换为 SystemMessage 并自动注入
- 如果传入空 prompt，需要在运行时覆盖
- 或者不使用 `create_react_agent` 的 prompt 参数，改为手动管理

### 方案二：使用 ChatPromptTemplate + 占位符（推荐用于新实现）

**实现思路**：
1. 在 Agent 创建时，使用 `ChatPromptTemplate` 定义消息结构（包含占位符）
2. 运行时通过状态传递动态数据
3. 在节点函数中，使用 `format_messages` 填充占位符

**代码示例**：

```python
# backend/domain/agents/factory.py (修改)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

@staticmethod
def create_agent(
    config: AgentNodeConfig,
    flow_dir: str,
    tools: Optional[List[BaseTool]] = None
) -> AgentExecutor:
    """创建Agent实例（使用ChatPromptTemplate）"""
    
    # 加载基础提示词
    base_prompt = prompt_manager.get_prompt(
        prompt_path=config.prompt,
        flow_dir=flow_dir
    )
    
    # 创建提示词模板（包含占位符）
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", f"""{base_prompt}

患者信息：
{{patient_info}}

医学参考资料：
{{rag_context}}
"""),  # 占位符用于运行时填充
        MessagesPlaceholder(variable_name="messages"),  # 历史消息和当前消息
    ])
    
    # 创建 LLM
    llm = get_llm(...)
    
    # 使用 create_react_agent（传入模板）
    graph = create_react_agent(
        model=llm,
        tools=agent_tools,
        prompt=prompt_template  # 传入模板而非字符串
    )
    
    return AgentExecutor(graph, agent_tools, base_prompt, verbose=True)

# backend/domain/flows/builder.py (修改节点函数)
def agent_node_action(state: FlowState) -> FlowState:
    """Agent节点函数（使用状态传递动态数据）"""
    
    # 1. 获取患者信息
    patient_info = get_patient_info(state.get("token_id"))
    patient_info_str = format_patient_info(patient_info)
    
    # 2. 获取 RAG 资料
    last_message = state.get("messages", [])[-1]
    rag_context = retrieve_medical_references(last_message.content)
    
    # 3. 将动态数据添加到状态
    # 注意：需要修改 FlowState 定义，添加 patient_info 和 rag_context 字段
    new_state = state.copy()
    new_state["patient_info"] = patient_info_str
    new_state["rag_context"] = rag_context
    
    # 4. 调用 Agent（Agent 内部会使用 ChatPromptTemplate 格式化消息）
    # 这里需要确保 create_react_agent 能正确处理模板
    result = agent_executor.invoke({"input": "...", **new_state})
    
    return new_state
```

**挑战**：
- `create_react_agent` 可能不完全支持 `ChatPromptTemplate` 的占位符填充
- 需要验证 LangGraph 是否支持通过状态传递占位符数据

### 方案三：在节点函数中手动构建消息列表（最灵活，推荐）

**实现思路**：
1. Agent 创建时，保存基础提示词和 LLM（不依赖 `create_react_agent` 的 prompt 参数）
2. 节点函数中，手动构建包含完整 SystemMessage 的消息列表
3. 使用 `create_react_agent` 的工具调用逻辑，但手动管理消息

**代码示例**：

```python
# backend/domain/agents/factory.py (修改)
class AgentExecutor:
    def __init__(self, llm: BaseChatModel, tools: List[BaseTool], base_prompt: str, verbose: bool = False):
        """
        初始化Agent执行器
        
        Args:
            llm: LLM客户端
            tools: 工具列表
            base_prompt: 基础系统提示词
            verbose: 是否输出详细信息
        """
        self.llm = llm
        self.tools = tools
        self.base_prompt = base_prompt
        self.verbose = verbose
        
        # 创建工具绑定的 LLM（用于工具调用）
        from langchain_core.tools import bind_tools
        self.llm_with_tools = bind_tools(self.llm, tools)
    
    def invoke_with_messages(self, messages: List[BaseMessage], callbacks: Optional[List] = None) -> dict:
        """
        使用消息列表调用Agent（支持运行时注入SystemMessage）
        
        Args:
            messages: 完整的消息列表（包含SystemMessage）
            callbacks: 回调处理器列表
            
        Returns:
            包含 "output" 和 "messages" 的字典
        """
        # 这里需要实现 ReAct 模式的工具调用逻辑
        # 或者使用 LangGraph 的 ToolNode 来执行工具调用
        # 简化示例（实际需要完整的 ReAct 循环）：
        
        from langchain_core.messages import AIMessage, ToolMessage
        
        # 调用 LLM（带工具绑定）
        response = self.llm_with_tools.invoke(messages, config={"callbacks": callbacks})
        
        # 检查是否有工具调用
        if hasattr(response, "tool_calls") and response.tool_calls:
            # 执行工具调用
            tool_results = []
            for tool_call in response.tool_calls:
                tool = next((t for t in self.tools if t.name == tool_call["name"]), None)
                if tool:
                    result = tool.invoke(tool_call["args"])
                    tool_results.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call["id"]
                    ))
            
            # 继续调用 LLM（包含工具结果）
            messages = messages + [response] + tool_results
            final_response = self.llm_with_tools.invoke(messages, config={"callbacks": callbacks})
            return {"output": final_response.content, "messages": messages + [final_response]}
        else:
            return {"output": response.content, "messages": messages + [response]}

# backend/domain/flows/builder.py (修改节点函数)
def agent_node_action(state: FlowState) -> FlowState:
    """Agent节点函数（手动构建消息列表）"""
    from langchain_core.messages import SystemMessage
    
    # 1. 获取基础系统提示词
    base_prompt = agent_executor.base_prompt
    
    # 2. 获取患者信息
    patient_info = get_patient_info(state.get("token_id"))
    patient_info_str = format_patient_info(patient_info)
    
    # 3. 获取 RAG 资料
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    rag_context = retrieve_medical_references(last_message.content if last_message else "")
    
    # 4. 构建完整系统提示词
    full_system_prompt = f"""{base_prompt}

患者信息：
{patient_info_str}

医学参考资料：
{rag_context}
"""
    
    # 5. 构建完整消息列表
    messages = [
        SystemMessage(content=full_system_prompt),
        *state.get("messages", [])  # 历史消息和当前消息
    ]
    
    # 6. 调用 Agent
    result = agent_executor.invoke_with_messages(messages)
    
    # 7. 更新状态
    new_state = state.copy()
    new_state["messages"] = result["messages"]
    
    return new_state
```

**优点**：
- ✅ 完全控制消息构建过程
- ✅ 灵活支持动态上下文注入
- ✅ 不依赖 `create_react_agent` 的 prompt 参数限制

**缺点**：
- ⚠️ 需要实现完整的 ReAct 工具调用逻辑（或使用 LangGraph ToolNode）
- ⚠️ 代码复杂度增加

---

## 🎯 最终推荐方案

### 推荐：方案三（手动构建消息列表）+ 简化实现

**具体建议**：

1. **保持基础提示词在编译时加载**（性能考虑）
2. **使用 `create_react_agent` 创建图，但传入空 prompt 或占位符**
3. **在节点函数中，动态构建完整 SystemMessage 并手动调用**

**简化实现思路**：

```python
# backend/domain/agents/factory.py
@staticmethod
def create_agent(...) -> AgentExecutor:
    # 加载基础提示词（保存，不直接传给 create_react_agent）
    base_prompt = prompt_manager.get_prompt(...)
    
    # 创建 LLM
    llm = get_llm(...)
    
    # 使用 create_react_agent（传入占位符，实际不使用）
    graph = create_react_agent(
        model=llm,
        tools=agent_tools,
        prompt=""  # 空 prompt 或占位符
    )
    
    return AgentExecutor(graph, agent_tools, base_prompt, llm, verbose=True)

# backend/domain/flows/builder.py
def agent_node_action(state: FlowState) -> FlowState:
    """Agent节点函数"""
    from langchain_core.messages import SystemMessage
    
    # 1. 获取基础提示词
    base_prompt = agent_executor.base_prompt
    
    # 2. 获取动态上下文
    patient_info = get_patient_info(state.get("token_id"))
    rag_context = retrieve_medical_references(...)
    
    # 3. 构建完整 SystemMessage
    full_system_prompt = f"""{base_prompt}

患者信息：
{format_patient_info(patient_info)}

医学参考资料：
{rag_context}
"""
    
    # 4. 构建消息列表（SystemMessage + 历史消息 + 当前消息）
    messages = [
        SystemMessage(content=full_system_prompt),
        *state.get("messages", [])
    ]
    
    # 5. 调用 Agent 图（传入完整消息列表）
    # 注意：需要修改 AgentExecutor.invoke 以支持直接传入消息列表
    result = agent_executor.graph.invoke(
        {"messages": messages},
        config={"configurable": {"thread_id": state.get("session_id")}}
    )
    
    # 6. 更新状态
    new_state = state.copy()
    new_state["messages"] = result.get("messages", [])
    
    return new_state
```

---

## 📊 方案对比总结

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **方案一：修改节点函数（运行时构建）** | 灵活，完全控制 | 需要修改 create_react_agent 使用方式 | ⭐⭐⭐⭐ |
| **方案二：ChatPromptTemplate + 占位符** | 符合 LangChain 规范 | 可能不完全支持 | ⭐⭐⭐ |
| **方案三：手动构建消息列表** | 最灵活，完全控制 | 代码复杂度较高 | ⭐⭐⭐⭐⭐ |

---

## ✅ 最终建议

基于您的代码结构和需求，**推荐使用方案四：包装节点函数**（最实际、改动最小）

### 推荐方案：包装节点函数，运行时动态注入

**核心思路**：
1. Agent 创建时，保存基础提示词（不改变当前实现）
2. 在节点函数中，包装 Agent 调用，动态构建完整 SystemMessage
3. 修改 AgentExecutor，支持传入完整消息列表

**实现步骤**：

#### 步骤1：修改 AgentExecutor，支持自定义消息列表

```python
# backend/domain/agents/factory.py (修改)
class AgentExecutor:
    def __init__(self, graph: Any, tools: List[BaseTool], base_prompt: str, llm: BaseChatModel, verbose: bool = False):
        self.graph = graph
        self.tools = tools
        self.base_prompt = base_prompt  # 新增：保存基础提示词
        self.llm = llm  # 新增：保存 LLM（用于未来扩展）
        self.verbose = verbose
    
    def invoke_with_custom_messages(self, messages: List[BaseMessage], config: dict = None) -> dict:
        """
        使用自定义消息列表调用Agent（支持运行时注入SystemMessage）
        
        Args:
            messages: 完整的消息列表（包含SystemMessage）
            config: 配置（可选）
            
        Returns:
            包含 "output" 和 "messages" 的字典
        """
        if config is None:
            config = {"configurable": {"thread_id": "default"}}
        
        # 直接调用图，传入完整消息列表
        result = self.graph.invoke({"messages": messages}, config)
        
        # 提取最后一条AI消息作为输出
        output = ""
        if result.get("messages"):
            for msg in reversed(result["messages"]):
                if hasattr(msg, "type") and msg.type == "ai":
                    output = msg.content if isinstance(msg.content, str) else str(msg.content)
                    break
        
        return {"output": output, "messages": result.get("messages", [])}
```

**注意**：这里有个问题，`create_react_agent` 创建的图会自动注入 SystemMessage（从 prompt 参数）。如果要覆盖，需要不同的方式。

#### 步骤2：实际可行的方案（推荐）

由于 `create_react_agent` 会自动注入 SystemMessage，我们需要采用**修改节点函数**的方式：

```python
# backend/domain/flows/builder.py (修改节点函数)
def agent_node_action(state: FlowState) -> FlowState:
    """Agent节点函数（运行时注入动态上下文）"""
    from langchain_core.messages import SystemMessage
    
    # 1. 获取基础系统提示词（从 AgentExecutor 获取）
    base_prompt = agent_executor.base_prompt
    
    # 2. 获取患者信息（从缓存接口）
    token_id = state.get("token_id")
    patient_info = get_patient_info_from_cache(token_id)  # 需要实现
    patient_info_str = format_patient_info(patient_info)  # 需要实现
    
    # 3. 获取 RAG 资料（医学参考资料）
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    user_query = last_message.content if last_message else ""
    rag_context = retrieve_medical_references(user_query)  # 需要实现
    
    # 4. 构建完整系统提示词
    full_system_prompt = f"""{base_prompt}

患者信息：
{patient_info_str}

医学参考资料：
{rag_context}
"""
    
    # 5. 构建完整消息列表（SystemMessage + 历史消息）
    messages = [
        SystemMessage(content=full_system_prompt),
        *state.get("messages", [])
    ]
    
    # 6. 问题：create_react_agent 创建的图会自动注入 SystemMessage
    # 解决方案A：不使用 create_react_agent 的 prompt 参数（传入空字符串或占位符）
    # 解决方案B：手动调用 LLM + 工具调用逻辑（不使用 create_react_agent 的图）
    
    # 这里提供解决方案A的实现思路：
    # 需要修改 AgentFactory.create_agent，使 create_react_agent 不传入 prompt
    # 但这样会失去系统提示词，所以需要在这里手动注入
    
    # 临时方案：直接调用图的内部逻辑
    # 注意：这需要了解 create_react_agent 的内部实现
    
    # 实际上，更简单的方案是：
    # 修改 AgentFactory，使 create_react_agent 传入空 prompt 或占位符
    # 然后在节点函数中手动构建完整的 SystemMessage
    
    # 7. 调用 Agent（使用修改后的方式）
    # 这里假设我们已经修改了 AgentFactory，使 graph 不会自动注入 SystemMessage
    config = {"configurable": {"thread_id": state.get("session_id", "default")}}
    
    # 由于 create_react_agent 会自动注入，我们需要采用不同的策略
    # 选项1：修改 AgentFactory，使用 ChatPromptTemplate（如果支持）
    # 选项2：不使用 create_react_agent，改为手动实现 Agent 逻辑
    # 选项3：接受 create_react_agent 的自动注入，但在基础提示词中使用占位符，运行时替换
    
    # 推荐：选项3（最简单，改动最小）
    # 在配置文件中使用占位符：{patient_info}, {rag_context}
    # 运行时替换占位符
    
    return new_state
```

**实际可行的最简单方案**：

考虑到 `create_react_agent` 的限制，推荐使用**占位符替换**的方式：

```python
# backend/domain/flows/builder.py (修改节点函数)
def agent_node_action(state: FlowState) -> FlowState:
    """Agent节点函数（运行时替换占位符）"""
    import re
    
    # 1. 获取基础系统提示词（包含占位符）
    base_prompt = agent_executor.base_prompt
    
    # 2. 获取动态数据
    token_id = state.get("token_id")
    patient_info = get_patient_info_from_cache(token_id)
    patient_info_str = format_patient_info(patient_info)
    
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    user_query = last_message.content if last_message else ""
    rag_context = retrieve_medical_references(user_query)
    
    # 3. 替换占位符（如果基础提示词中包含占位符）
    # 注意：需要在配置文件中使用占位符格式，如 {patient_info}, {rag_context}
    full_prompt = base_prompt.replace("{patient_info}", patient_info_str)
    full_prompt = full_prompt.replace("{rag_context}", rag_context)
    
    # 4. 问题：create_react_agent 的 prompt 已经在编译时绑定
    # 所以我们需要在 Agent 创建时传入模板，而不是直接替换
    
    # 更实际的方案：修改 AgentFactory，使用 ChatPromptTemplate
    # 或者：接受 create_react_agent 的限制，在基础提示词中不包含占位符
    # 而是通过其他方式注入（如通过消息列表）
    
    # 但 create_react_agent 会自动注入 SystemMessage，所以我们无法在运行时修改
    
    return new_state
```

**结论**：由于 `create_react_agent` 的限制，**最实际的方案是修改 AgentFactory，使用 ChatPromptTemplate 或在节点函数中手动调用 LLM**。

### 最终推荐：修改 AgentFactory 使用 ChatPromptTemplate（如果支持）

```python
# backend/domain/agents/factory.py (修改)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

@staticmethod
def create_agent(...) -> AgentExecutor:
    # 加载基础提示词
    base_prompt = prompt_manager.get_prompt(...)
    
    # 创建提示词模板（包含占位符）
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", f"""{base_prompt}

患者信息：
{{patient_info}}

医学参考资料：
{{rag_context}}
"""),  # 使用占位符
        MessagesPlaceholder(variable_name="messages"),
    ])
    
    # 创建 LLM
    llm = get_llm(...)
    
    # 使用 create_react_agent（传入模板）
    # 注意：需要验证 create_react_agent 是否支持 ChatPromptTemplate
    try:
        graph = create_react_agent(
            model=llm,
            tools=agent_tools,
            prompt=prompt_template
        )
    except Exception as e:
        logger.warning(f"create_react_agent 不支持 ChatPromptTemplate，使用字符串: {e}")
        # 降级方案：使用字符串 prompt
        graph = create_react_agent(
            model=llm,
            tools=agent_tools,
            prompt=base_prompt
        )
    
    return AgentExecutor(graph, agent_tools, base_prompt, llm, verbose=True)
```

**注意**：需要验证 `create_react_agent` 是否支持 `ChatPromptTemplate`。如果不支持，需要采用其他方案。

---

## 📋 总结回答您的问题

### 1. 系统提示词是否应该运行时设置？

**推荐：混合方案（编译时 + 运行时）**
- ✅ **基础提示词**（静态部分）：编译时加载（保持当前实现）
- ✅ **动态内容**（患者信息、RAG）：运行时注入
- ❌ **不完全运行时**：避免每次请求都读取文件

**原因**：
- 性能：基础提示词在编译时加载，避免重复读取
- 灵活性：动态内容在运行时注入，支持个性化
- 代码清晰：静态配置与动态数据分离

### 2. 对话历史和当前消息是否运行时注入？

**✅ 是的，当前实现正确**
- 对话历史：运行时通过 `messages` 传入 ✅
- 当前消息：运行时通过 `messages` 传入 ✅
- 保持当前实现即可

### 3. RAG 信息和患者信息是否放在 SystemMessage 中？

**✅ 是的，推荐放在 SystemMessage 中**

**原因**：
- ✅ 语义清晰：这些是上下文信息，不是对话历史
- ✅ 模型理解：LLM 能更好地区分系统指令和上下文数据
- ✅ Token 效率：放在 SystemMessage 中，模型知道这是参考信息
- ✅ 灵活性：可以根据请求动态调整内容

**实现方式**：
- 患者信息：运行时从缓存接口获取，注入到 SystemMessage ✅
- 医学参考资料：运行时 RAG 检索，注入到 SystemMessage ✅

---

## 🔧 具体实施建议

### 方案选择

基于您的代码结构和 `create_react_agent` 的限制，推荐：

1. **如果 `create_react_agent` 支持 ChatPromptTemplate**：
   - 使用 ChatPromptTemplate + 占位符（方案二）

2. **如果 `create_react_agent` 不支持 ChatPromptTemplate**：
   - 方案A：修改 AgentFactory，不使用 `create_react_agent` 的 prompt 参数，改为在节点函数中手动构建 SystemMessage
   - 方案B：接受限制，在基础提示词中使用占位符，但需要在 Agent 创建时动态替换（较复杂）

### 推荐实施路径

1. **第一步**：验证 `create_react_agent` 是否支持 `ChatPromptTemplate`
2. **第二步**：如果支持，使用 ChatPromptTemplate 方案
3. **第三步**：如果不支持，采用节点函数中手动构建 SystemMessage 的方案

**核心原则**：
- 静态内容（基础提示词）→ 编译时加载
- 动态内容（患者信息、RAG）→ 运行时注入到 SystemMessage
- 对话内容（历史、当前）→ 运行时通过 messages 传入（已正确实现）✅

