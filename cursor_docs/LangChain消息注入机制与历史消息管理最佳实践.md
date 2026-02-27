# LangChain 消息注入机制与历史消息管理最佳实践

## 📚 目录

1. [SystemMessage 的注入方式与时机](#systemmessage-的注入方式与时机)
2. [用户消息的注入方式](#用户消息的注入方式)
3. [历史消息的管理方式](#历史消息的管理方式)
4. [行业最佳实践总结](#行业最佳实践总结)

---

## SystemMessage 的注入方式与时机

### 1.1 注入时机：编译阶段 vs 运行时

**关键结论：SystemMessage 的注入时机取决于使用的 API，主要有两种模式：**

#### 模式一：编译阶段注入（通过 Prompt 参数）

**使用场景**：使用 `create_react_agent`、`create_agent` 等预构建函数

```python
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate

# 方式1：直接传入字符串（会被转换为 SystemMessage）
agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt="你是一个专业的医疗助手..."  # 编译时转换为 SystemMessage
)

# 方式2：使用 ChatPromptTemplate（更灵活）
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个专业的医疗助手..."),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="chat_history")
])
agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=prompt  # 编译时绑定到 Agent
)
```

**机制说明**：
- `create_react_agent` 在**编译阶段**将 `prompt` 参数转换为内部的提示词模板
- 每次调用 Agent 时，系统提示词会**自动插入**到消息列表的开头
- 这是 LangGraph/LangChain 的内部机制，用户无需手动管理

#### 模式二：运行时注入（直接在消息列表中）

**使用场景**：直接调用 LLM 或使用自定义节点函数

```python
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# 方式1：在消息列表开头添加 SystemMessage
messages = [
    SystemMessage(content="你是一个专业的医疗助手..."),
    HumanMessage(content="我想记录血压"),
]

response = llm.invoke(messages)

# 方式2：在 LangGraph 节点函数中动态添加
def agent_node(state):
    messages = state["messages"]
    
    # 动态构建系统消息（可能包含运行时数据）
    system_msg = SystemMessage(
        content=f"当前用户ID: {state['user_id']}\n系统提示词..."
    )
    
    # 合并消息（系统消息在前）
    all_messages = [system_msg] + messages
    response = llm.invoke(all_messages)
    return {"messages": [response]}
```

**机制说明**：
- 系统消息作为 `SystemMessage` 对象直接添加到消息列表
- 必须在每次调用时手动管理
- 适用于需要动态生成系统提示词的场景

### 1.2 不同模型提供商的适配

LangChain 会根据模型提供商自动适配 SystemMessage：

1. **支持 System 角色的模型**（如 OpenAI GPT-4、Claude）：
   - SystemMessage 作为消息列表的一部分，角色设置为 "system"
   
2. **通过单独 API 参数传递**（如某些开源模型）：
   - LangChain 自动提取 SystemMessage 内容，通过 `system` 参数传递
   
3. **不支持系统消息的模型**：
   - SystemMessage 会被转换为 HumanMessage 或忽略

### 1.3 当前项目的实现方式

```127:131:backend/domain/agents/factory.py
        # 使用LangGraph的create_react_agent创建图
        graph = create_react_agent(
            model=llm,
            tools=agent_tools,
            prompt=prompt_content  # 直接传入提示词字符串
        )
```

**特点**：
- ✅ 使用编译时注入（通过 `prompt` 参数）
- ✅ 系统提示词在 Agent 创建时绑定
- ✅ 每次调用时自动注入，无需手动管理

---

## 用户消息的注入方式

### 2.1 代码写法（多种模式）

#### 方式1：LangGraph 状态管理（推荐）

**使用场景**：LangGraph 流程中

```python
from langchain_core.messages import HumanMessage, AIMessage
from typing import TypedDict

class FlowState(TypedDict):
    messages: list  # 消息列表
    session_id: str

# 在 API 入口处构建初始状态
def chat_handler(request):
    messages = []
    
    # 添加历史消息
    if request.conversation_history:
        for msg in request.conversation_history:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))
    
    # 添加当前用户消息
    messages.append(HumanMessage(content=request.message))
    
    # 构建状态
    initial_state = {
        "messages": messages,
        "session_id": request.session_id
    }
    
    # 执行图
    result = graph.invoke(initial_state, config={"configurable": {"thread_id": request.session_id}})
    return result
```

**当前项目实现**：

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

#### 方式2：直接调用 LLM

```python
from langchain_core.messages import HumanMessage

# 简单场景：单个消息
response = llm.invoke([HumanMessage(content="你好")])

# 或者直接传入字符串（LangChain 自动转换）
response = llm.invoke("你好")
```

#### 方式3：在节点函数中动态添加

```python
def my_node(state):
    # 从状态中获取消息
    messages = state.get("messages", [])
    
    # 动态添加新消息
    new_message = HumanMessage(content="动态生成的内容")
    messages.append(new_message)
    
    # 调用 LLM
    response = llm.invoke(messages)
    return {"messages": [response]}
```

#### 方式4：使用 ChatPromptTemplate（结构化方式）

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个助手"),
    MessagesPlaceholder(variable_name="history"),  # 历史消息占位符
    ("human", "{input}")  # 当前用户输入
])

# 填充模板
formatted = prompt.format_messages(
    history=[HumanMessage(content="历史消息1"), AIMessage(content="回复1")],
    input="当前用户消息"
)

response = llm.invoke(formatted)
```

### 2.2 消息注入的时机

**关键点**：用户消息通常在**运行时注入**，而不是编译时：

1. **API 入口处**：接收用户请求后立即构建消息列表
2. **节点执行时**：在节点函数中动态添加或修改消息
3. **状态更新时**：通过状态更新机制添加新消息

---

## 历史消息的管理方式

### 3.1 方式对比

#### 方式一：放在系统提示词中（不推荐用于长对话）

**实现方式**：

```python
# 将历史消息转换为文本，嵌入系统提示词
history_text = "\n".join([
    f"用户: {msg.content}" if isinstance(msg, HumanMessage) 
    else f"助手: {msg.content}"
    for msg in conversation_history
])

system_prompt = f"""
你是一个助手。以下是对话历史：
{history_text}

请基于以上历史继续对话。
"""

agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=system_prompt
)
```

**优点**：
- ✅ 实现简单
- ✅ 适合历史消息较少的情况（< 5 轮对话）

**缺点**：
- ❌ 提示词长度快速增长，占用 token 配额
- ❌ 超过模型上下文窗口会出错
- ❌ 无法利用模型的原生对话理解能力
- ❌ 历史消息和系统指令混合，语义不清晰

#### 方式二：作为消息列表的一部分（推荐）

**实现方式**：

```python
# 方式1：完整消息列表（最常用）
messages = [
    SystemMessage(content="系统提示词"),  # 系统消息在前
    HumanMessage(content="用户消息1"),
    AIMessage(content="助手回复1"),
    HumanMessage(content="用户消息2"),
    AIMessage(content="助手回复2"),
    HumanMessage(content="当前用户消息"),  # 最新消息在最后
]

response = llm.invoke(messages)

# 方式2：使用 ChatPromptTemplate
prompt = ChatPromptTemplate.from_messages([
    ("system", "系统提示词"),
    MessagesPlaceholder(variable_name="history"),  # 历史消息占位符
    ("human", "{input}")
])

formatted = prompt.format_messages(
    history=conversation_history,  # 历史消息列表
    input="当前用户消息"
)
```

**优点**：
- ✅ 语义清晰：系统消息、历史消息、当前消息分离
- ✅ 模型原生支持：LLM 能更好地理解对话结构
- ✅ Token 效率高：只包含必要的消息内容
- ✅ 灵活：可以动态添加/删除历史消息
- ✅ 符合 LangChain/LangGraph 的设计理念

**缺点**：
- ⚠️ 需要手动管理消息列表
- ⚠️ 长对话仍然可能超过上下文窗口（需要摘要或截断）

#### 方式三：使用 Memory 机制（LangChain 原生支持）

**实现方式**：

```python
from langchain.memory import ConversationBufferMemory, ConversationSummaryMemory
from langchain.chains import ConversationChain

# 方式1：完整历史记录（适合短对话）
memory = ConversationBufferMemory()
memory.chat_memory.add_user_message("用户消息1")
memory.chat_memory.add_ai_message("助手回复1")

# 方式2：摘要历史（适合长对话）
memory = ConversationSummaryMemory(llm=llm)
memory.save_context({"input": "用户消息1"}, {"output": "助手回复1"})

# 使用 Memory
chain = ConversationChain(
    llm=llm,
    memory=memory,
    verbose=True
)

response = chain.predict(input="当前用户消息")
```

**优点**：
- ✅ LangChain 原生支持，API 简洁
- ✅ 自动管理消息格式转换
- ✅ 支持摘要、窗口等高级功能

**缺点**：
- ⚠️ 主要适用于简单的链式调用
- ⚠️ 在 LangGraph 中需要手动集成

#### 方式四：使用 Checkpointer（LangGraph 推荐）

**实现方式**：

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import AsyncPostgresSaver

# 创建 Checkpointer
checkpointer = AsyncPostgresSaver.from_conn_string("postgresql://...")
# 或使用内存版本（开发测试）
checkpointer = MemorySaver()

# 编译图时绑定 Checkpointer
graph = graph.compile(checkpointer=checkpointer)

# 运行时使用 thread_id 恢复历史状态
config = {"configurable": {"thread_id": session_id}}
result = graph.invoke(initial_state, config=config)
```

**当前项目实现**：

```127:128:backend/app/api/routes/chat.py
            config = {"configurable": {"thread_id": request.session_id}}
            result = graph.invoke(initial_state, config)
```

**优点**：
- ✅ 自动状态持久化：每次节点执行后自动保存
- ✅ 自动状态恢复：使用相同的 `thread_id` 自动恢复历史状态
- ✅ 支持多轮对话：状态包含消息历史、意图、上下文等
- ✅ 分布式友好：状态存储在数据库，支持多实例部署
- ✅ LangGraph 最佳实践

**缺点**：
- ⚠️ 需要配置数据库（生产环境）
- ⚠️ 状态恢复可能包含大量数据（需要合理设计状态结构）

### 3.2 RAG 资料和用户信息的注入

#### 方式一：放在系统提示词中（适合静态信息）

```python
# RAG 检索结果
rag_context = """
根据检索到的资料：
1. 用户的基本信息：年龄 35 岁，有高血压病史
2. 相关医学知识：正常血压范围是 120/80 mmHg
"""

system_prompt = f"""
你是一个医疗助手。以下是用户信息和相关知识：

{rag_context}

请基于以上信息回答问题。
"""

agent = create_react_agent(model=llm, tools=tools, prompt=system_prompt)
```

#### 方式二：作为独立消息注入（推荐，适合动态信息）

```python
from langchain_core.messages import SystemMessage, HumanMessage

# 方式1：作为 SystemMessage 的一部分（运行时注入）
def agent_node(state):
    # 动态检索 RAG 资料
    rag_context = retrieve_context(state["query"])
    user_info = get_user_info(state["user_id"])
    
    # 构建包含上下文的消息列表
    messages = [
        SystemMessage(content=f"系统提示词\n\n用户信息：{user_info}\n相关上下文：{rag_context}"),
        *state["messages"]  # 历史消息和当前消息
    ]
    
    response = llm.invoke(messages)
    return {"messages": [response]}

# 方式2：使用 ToolMessage（适合工具调用场景）
from langchain_core.messages import ToolMessage, AIMessage

# ⚠️ 重要：ToolMessage 必须与对应的 AIMessage 配对
# 正确的消息序列应该是：
# HumanMessage → AIMessage(tool_calls) → ToolMessage → AIMessage(最终回复)

# 示例：如果 RAG 是通过工具调用检索的
messages = [
    SystemMessage(content="系统提示词"),
    *conversation_history,
    HumanMessage(content="用户问题"),
    # Agent 会生成 AIMessage，包含 tool_calls（如调用 rag_search 工具）
    AIMessage(
        content="",
        tool_calls=[{
            "name": "rag_search",
            "args": {"query": "用户问题"},
            "id": "call_rag_123"  # 工具调用 ID
        }]
    ),
    # ToolMessage 必须在对应的 AIMessage 之后，tool_call_id 必须匹配
    ToolMessage(
        content=rag_context,
        tool_call_id="call_rag_123"  # 必须与 AIMessage.tool_calls[].id 匹配
    ),
    # Agent 基于 ToolMessage 生成最终回复
    AIMessage(content="基于检索结果的回复...")
]

# ⚠️ 错误示例（不要这样做）：
# messages = [
#     SystemMessage(content="系统提示词"),
#     HumanMessage(content="用户问题"),
#     ToolMessage(...)  # ❌ 错误：ToolMessage 不能直接在 HumanMessage 之后
# ]
```

**关键点**：
1. **ToolMessage 的位置要求**：
   - ✅ ToolMessage 必须在包含 `tool_calls` 的 AIMessage 之后
   - ✅ ToolMessage 的 `tool_call_id` 必须与对应 `tool_call.id` 匹配
   - ❌ ToolMessage 不能直接在 HumanMessage 之后（没有对应的 tool_call）

2. **RAG 上下文的手动注入**（不是通过工具调用）：
```python
# 如果 RAG 是手动检索的（不是通过工具调用），应该放在 SystemMessage 中
rag_context = retrieve_context("用户问题")

messages = [
    SystemMessage(content=f"系统提示词\n\n相关上下文：\n{rag_context}"),
    *conversation_history,
    HumanMessage(content="用户问题")
]
```
```

### 3.2.1 ToolMessage 的正确用法和顺序要求

**关键规则**：ToolMessage 必须与对应的 AIMessage 配对，不能独立存在。

#### ✅ 正确的消息序列

```python
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

# 正确的工具调用序列
messages = [
    SystemMessage(content="系统提示词"),
    *conversation_history,
    HumanMessage(content="用户问题"),
    # 1. AIMessage 包含 tool_calls（LLM 决定调用工具）
    AIMessage(
        content="",
        tool_calls=[{
            "name": "search_tool",
            "args": {"query": "用户问题"},
            "id": "call_abc123"  # 工具调用 ID
        }]
    ),
    # 2. ToolMessage 必须在对应的 AIMessage 之后
    ToolMessage(
        content="工具执行结果",
        tool_call_id="call_abc123"  # 必须与 AIMessage.tool_calls[].id 匹配
    ),
    # 3. LLM 基于 ToolMessage 生成最终回复
    AIMessage(content="基于工具结果的最终回复")
]
```

**顺序要求**：
1. ✅ `HumanMessage` → `AIMessage(tool_calls)` → `ToolMessage` → `AIMessage(最终回复)`
2. ✅ `ToolMessage.tool_call_id` 必须与 `AIMessage.tool_calls[].id` 匹配
3. ✅ 如果有多个工具调用，每个 `ToolMessage` 对应一个 `tool_call`

#### ❌ 错误示例

```python
# 错误1：ToolMessage 直接在 HumanMessage 之后（没有对应的 tool_call）
messages = [
    HumanMessage(content="用户问题"),
    ToolMessage(content="结果", tool_call_id="xxx")  # ❌ 错误：没有对应的 AIMessage
]

# 错误2：ToolMessage 在 SystemMessage 中（语法错误）
messages = [
    SystemMessage(content="系统提示词"),
    ToolMessage(...)  # ❌ 错误：ToolMessage 不是系统消息的一部分
]

# 错误3：tool_call_id 不匹配
messages = [
    AIMessage(tool_calls=[{"id": "call_123"}]),
    ToolMessage(tool_call_id="call_456")  # ❌ 错误：ID 不匹配
]
```

#### RAG 上下文的两种注入方式

**方式1：手动检索，放在 SystemMessage 中**（推荐用于简单场景）

```python
# 手动检索 RAG 上下文
rag_context = retrieve_context("用户问题")

messages = [
    SystemMessage(content=f"系统提示词\n\n相关上下文：\n{rag_context}"),
    *conversation_history,
    HumanMessage(content="用户问题")
]
```

**方式2：通过工具调用检索，使用 ToolMessage**（适合工具化场景）

```python
# 如果 RAG 是通过工具调用的（如 create_react_agent 中的工具）
# 消息序列会自动生成：
# 1. HumanMessage("用户问题")
# 2. AIMessage(tool_calls=[{"name": "rag_search", ...}])
# 3. ToolMessage(content=rag_context, tool_call_id=...)
# 4. AIMessage("最终回复")

# 这是 LangGraph/LangChain Agent 自动处理的，不需要手动构建
```

**实际项目中的示例**（来自 `cursor_docs/001代码链路-Agent执行路径与数据流转分析.md`）：

```python
# Agent节点执行后的消息序列
messages = [
    HumanMessage("我想记录血压"),
    HumanMessage("今天血压120/80"),
    AIMessage("我来帮您记录血压数据..."),  # 包含 tool_calls
    ToolMessage(record_blood_pressure结果),  # 工具执行结果
    AIMessage("已成功记录您的血压数据：120/80")  # 最终回复
]
```

### 3.3 行业最佳实践总结

| 场景 | 推荐方式 | 原因 |
|------|---------|------|
| **短对话历史（< 5 轮）** | 消息列表 | 简单直接，模型理解好 |
| **长对话历史（> 10 轮）** | Checkpointer + 消息摘要 | 避免上下文溢出，保持状态 |
| **LangGraph 流程** | Checkpointer | LangGraph 原生支持，自动管理 |
| **RAG 上下文** | 运行时注入（SystemMessage 或 ToolMessage） | 动态检索，灵活更新 |
| **用户基础信息** | 系统提示词（编译时）或运行时注入 | 根据变更频率选择 |
| **工具调用结果** | ToolMessage | 符合 LangChain 规范 |

---

## 行业最佳实践总结

### 4.1 消息注入时机总结

```
编译阶段（图构建时）：
  ├─ SystemMessage（通过 prompt 参数）
  ├─ Agent 配置（工具、模型等）
  └─ 图结构定义

运行时（请求处理时）：
  ├─ HumanMessage（用户当前输入）
  ├─ 历史消息（从 Checkpointer 恢复或手动构建）
  ├─ 动态 SystemMessage（需要运行时数据时）
  ├─ RAG 上下文（检索结果）
  └─ ToolMessage（工具执行结果）
```

### 4.2 推荐实践

#### ✅ 推荐做法

1. **SystemMessage 使用编译时注入**（通过 `prompt` 参数）
   - 性能好，逻辑清晰
   - 适合静态系统提示词

2. **历史消息使用 Checkpointer 管理**（LangGraph 场景）
   - 自动持久化和恢复
   - 支持复杂的对话状态

3. **RAG 上下文运行时注入**
   - 作为 SystemMessage 的一部分或 ToolMessage
   - 根据查询动态检索

4. **用户消息通过状态管理**
   - 在 API 入口构建初始状态
   - 使用 `messages` 字段传递

#### ❌ 不推荐做法

1. **将长对话历史放入系统提示词**
   - Token 浪费
   - 容易超出上下文窗口

2. **每次手动重建完整消息列表**（有 Checkpointer 时）
   - 应该利用 Checkpointer 的自动恢复功能

3. **混合使用多种历史消息管理方式**
   - 选择一种统一的方式，避免混乱

### 4.3 当前项目的优化建议

**当前实现分析**：

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

**潜在问题**：
- 如果使用了 Checkpointer，`conversation_history` 参数可能是冗余的
- Checkpointer 会自动恢复历史状态，手动传递历史消息可能导致重复

**优化建议**：

```python
# 方案1：优先使用 Checkpointer（推荐）
messages = [HumanMessage(content=request.message)]  # 只添加当前消息
initial_state = {"messages": messages, ...}
config = {"configurable": {"thread_id": request.session_id}}
result = graph.invoke(initial_state, config=config)
# Checkpointer 会自动合并历史状态和当前消息

# 方案2：如果必须支持 conversation_history（兼容性考虑）
# 检查是否有 Checkpointer
if has_checkpointer:
    # 优先使用 Checkpointer，忽略 conversation_history
    messages = [HumanMessage(content=request.message)]
else:
    # 降级方案：手动构建消息列表
    messages = build_messages_from_history(request.conversation_history)
    messages.append(HumanMessage(content=request.message))
```

---

## 参考资料

1. **LangChain 官方文档**：
   - [Messages](https://python.langchain.com/docs/concepts/messages)
   - [Memory](https://python.langchain.com/docs/expression_language/how_to/message_history)
   - [LangGraph Checkpointer](https://langchain-ai.github.io/langgraph/concepts/persistence/)

2. **行业实践**：
   - OpenAI API 文档：系统消息最佳实践
   - Anthropic Claude API：消息格式说明
   - LangChain Cookbook：多轮对话示例

3. **当前项目文档**：
   - `cursor_docs/001代码链路-Agent执行路径与数据流转分析.md`
   - `cursor_docs/学习知识/Checkpointer机制详解.md`

---

**文档生成时间**：2025-01-XX  
**适用版本**：LangChain 1.x, LangGraph 0.2+

