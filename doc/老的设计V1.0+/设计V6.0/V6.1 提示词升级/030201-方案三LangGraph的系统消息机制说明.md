# 方案三：LangGraph 系统消息机制详细说明

## 一、LangGraph 系统消息机制原理

### 1.1 核心概念

LangGraph 中的系统消息（System Message）是 LangChain 消息系统的一部分，用于向 LLM 提供指令、上下文和角色定义。系统消息在消息列表中有特殊的地位：

1. **消息类型**：`SystemMessage` 是 LangChain 的核心消息类型之一
2. **处理顺序**：系统消息通常放在消息列表的开头，LLM 会优先处理
3. **持久化**：通过 LangGraph 的 checkpointer 机制，系统消息可以被持久化和恢复
4. **动态注入**：可以在运行时动态添加、修改或替换系统消息

### 1.2 create_react_agent 的提示词处理机制

`create_react_agent` 是 LangGraph 提供的预构建 Agent，它使用 `prompt` 参数来设置系统提示词：

```python
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=system_prompt  # 系统提示词
)
```

**内部机制**：
1. `create_react_agent` 会将 `prompt` 参数转换为 `SystemMessage`
2. 在每次调用 Agent 时，系统消息会被自动插入到消息列表的开头
3. 如果消息列表中已经存在 `SystemMessage`，`create_react_agent` 可能会：
   - 替换现有的系统消息（取决于实现）
   - 或者在现有系统消息前添加新的系统消息

### 1.3 运行时系统消息注入

在 LangGraph 中，可以在运行时动态注入系统消息：

```python
from langchain_core.messages import SystemMessage, HumanMessage

# 运行时注入系统消息
messages = [
    SystemMessage(content="动态生成的系统提示词"),  # 运行时注入
    HumanMessage(content="用户消息"),
    # ... 其他消息
]

# 调用 Agent
result = await agent.ainvoke({"messages": messages})
```

**关键点**：
- 系统消息在消息列表中的位置很重要（通常放在开头）
- 可以有多条系统消息，LLM 会按顺序处理
- 系统消息可以通过 checkpointer 持久化，在后续对话中保持

### 1.4 消息列表的处理流程

```
消息列表结构：
[
    SystemMessage(content="基础系统提示词"),      # Agent 创建时设置
    SystemMessage(content="动态上下文信息"),      # 运行时注入
    HumanMessage(content="用户消息1"),
    AIMessage(content="助手回复1"),
    HumanMessage(content="用户消息2"),
    # ...
]
```

LLM 处理顺序：
1. 首先读取所有系统消息（按顺序）
2. 然后处理用户消息和助手消息的对话历史
3. 最后生成回复

## 二、代码示例

### 2.1 当前代码实现（问题版本）

**Agent 创建时**（`domain/agents/factory.py`）：

```python
# 在 _create_agent_internal 方法中
system_prompt = load_prompt_template()  # 加载提示词模板，包含 {{user_id}} 等占位符

# 填充占位符（但 state=None，只能填充时间相关占位符）
placeholders = PlaceholderManager.get_placeholders(agent_key, state=None)
system_prompt = PlaceholderManager.fill_placeholders(system_prompt, placeholders)
# 结果：{{user_id}}, {{session_id}} 等占位符未被替换

# 创建 Agent
agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=system_prompt  # 包含未替换占位符的提示词
)
```

**运行时调用**（`domain/router/graph.py`）：

```python
async def _run(state: RouterState) -> RouterState:
    messages = state.get("messages", [])
    
    # 当前代码只注入 user_info 相关的系统消息
    if user_id and not has_context:
        user_info_prompt = _prompt_manager.render(...)
        system_hint = SystemMessage(content=user_info_prompt)
        messages = [system_hint, *messages]
    
    # 调用 Agent（但 Agent 内部的系统消息仍包含未替换的占位符）
    result = await agent_node.ainvoke({"messages": messages})
```

### 2.2 方案三：使用 LangGraph 系统消息机制（改造后）

#### 2.2.1 Agent 创建时（修改 `domain/agents/factory.py`）

```python
def _create_agent_internal(
    cls,
    agent_key: str,
    llm: Optional[BaseChatModel] = None,
    tools: Optional[List[BaseTool]] = None
) -> CompiledStateGraph:
    """创建 Agent，使用基础提示词（不包含动态占位符）"""
    
    # 1. 加载提示词模板
    system_prompt = load_prompt_template()  # 包含 {{user_id}} 等占位符
    
    # 2. 只填充不依赖 state 的占位符（如时间相关）
    time_placeholders = {
        "current_date": datetime.now().strftime("%Y-%m-%d"),
        "current_time": datetime.now().strftime("%H:%M:%S"),
        "current_datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    # 注意：保留 {{user_id}}, {{session_id}}, {{user_info}}, {{history_msg}} 等占位符
    
    # 3. 创建 Agent（使用包含占位符的提示词，占位符将在运行时替换）
    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt  # 包含占位符的提示词
    )
    
    return agent
```

#### 2.2.2 运行时系统消息注入（修改 `domain/router/graph.py`）

```python
def with_user_context(agent_node, agent_name: str):
    """为智能体包装系统指令，动态注入完整的上下文信息"""
    
    async def _run(state: RouterState) -> RouterState:
        messages = state.get("messages", [])
        user_id = state.get("user_id")
        session_id = state.get("session_id")
        
        # 1. 从 state 中获取所有占位符值
        placeholders = PlaceholderManager.get_placeholders(agent_name, state=state)
        # 返回：{
        #     "user_id": "user123",
        #     "session_id": "session456",
        #     "current_date": "2025-12-30",
        #     "user_info": "患者基础信息...",
        #     "history_msg": "历史对话...",
        #     ...
        # }
        
        # 2. 加载原始提示词模板（包含占位符）
        from infrastructure.prompts.langfuse_adapter import LangfusePromptAdapter
        adapter = LangfusePromptAdapter()
        agent_config = AgentFactory._config.get(agent_name, {})
        langfuse_template = agent_config.get("langfuse_template")
        
        # 从 Langfuse 或本地文件加载模板
        if settings.PROMPT_SOURCE_MODE.lower() in ("langfuse", "auto"):
            try:
                template = adapter.get_template(langfuse_template)
            except:
                # 回退到本地文件
                local_file = Path("config/prompts/local") / f"{langfuse_template}.txt"
                with open(local_file, "r", encoding="utf-8") as f:
                    template = f.read()
        else:
            local_file = Path("config/prompts/local") / f"{langfuse_template}.txt"
            with open(local_file, "r", encoding="utf-8") as f:
                template = f.read()
        
        # 3. 填充占位符，生成完整的系统提示词
        filled_prompt = PlaceholderManager.fill_placeholders(template, placeholders)
        
        # 4. 创建系统消息（包含完整的上下文信息）
        system_message = SystemMessage(content=filled_prompt)
        
        # 5. 处理消息列表：替换或添加系统消息
        # 移除 Agent 创建时注入的系统消息（如果存在）
        filtered_messages = [
            msg for msg in messages 
            if not isinstance(msg, SystemMessage) or 
               not (hasattr(msg, 'content') and '{{' in str(msg.content))
        ]
        
        # 在消息列表开头插入新的系统消息
        messages_with_context = [system_message, *filtered_messages]
        
        logger.info(
            f"[AGENT_CONTEXT] 注入完整系统提示词: {agent_name}, "
            f"user_id={user_id}, session_id={session_id}"
        )
        
        # 6. 调用 Agent
        result = await agent_node.ainvoke({"messages": messages_with_context})
        
        # 7. 保留路由状态
        for key in ("session_id", "user_id", "current_intent", "current_agent", "need_reroute", "trace_id"):
            if key in state and key not in result:
                result[key] = state[key]
        
        return result
    
    _run.__name__ = f"{agent_name}_with_user_context"
    return _run
```

#### 2.2.3 简化版本（推荐）

如果不想在运行时重新加载模板，可以优化为：

```python
async def _run(state: RouterState) -> RouterState:
    messages = state.get("messages", [])
    
    # 1. 获取占位符值
    placeholders = PlaceholderManager.get_placeholders(agent_name, state=state)
    
    # 2. 查找并替换系统消息中的占位符
    # 假设 Agent 创建时的系统消息已经包含占位符
    updated_messages = []
    system_replaced = False
    
    for msg in messages:
        if isinstance(msg, SystemMessage) and not system_replaced:
            # 替换系统消息中的占位符
            original_content = msg.content
            filled_content = PlaceholderManager.fill_placeholders(original_content, placeholders)
            
            if original_content != filled_content:
                updated_messages.append(SystemMessage(content=filled_content))
                system_replaced = True
                logger.debug(f"已替换系统消息中的占位符: {agent_name}")
            else:
                updated_messages.append(msg)
        else:
            updated_messages.append(msg)
    
    # 3. 如果没有系统消息，添加一个
    if not system_replaced:
        # 需要加载模板并填充（这里简化处理）
        # 实际实现中需要从 Agent 配置中获取模板
        template = get_agent_template(agent_name)  # 需要实现此函数
        filled_prompt = PlaceholderManager.fill_placeholders(template, placeholders)
        updated_messages.insert(0, SystemMessage(content=filled_prompt))
    
    # 4. 调用 Agent
    result = await agent_node.ainvoke({"messages": updated_messages})
    
    return result
```

## 三、改造代价分析

### 3.1 代码修改范围

#### 需要修改的文件

1. **`domain/agents/factory.py`**
   - 修改 `_create_agent_internal` 方法
   - 修改占位符填充逻辑（只填充时间相关占位符）
   - **修改量**：中等（约 10-20 行）

2. **`domain/router/graph.py`**
   - 修改 `with_user_context` 函数
   - 添加运行时占位符替换逻辑
   - 添加系统消息处理逻辑
   - **修改量**：较大（约 30-50 行）

3. **`infrastructure/prompts/placeholder.py`**
   - 可能需要添加辅助方法（如获取 Agent 模板）
   - **修改量**：小（可选，约 5-10 行）

#### 新增依赖

- 可能需要添加模板加载的辅助函数
- 需要确保能够访问 Agent 配置和模板路径

### 3.2 性能影响

#### 正面影响

1. **Agent 缓存机制不受影响**
   - Agent 仍然可以在创建时缓存
   - 运行时只是修改消息列表，不影响 Agent 本身

2. **内存使用**
   - 每个请求需要动态生成系统消息（内存占用很小）
   - 不需要为每个用户/会话创建独立的 Agent 实例

#### 潜在影响

1. **运行时开销**
   - 每次调用 Agent 都需要：
     - 获取占位符值（从 state 中提取，开销很小）
     - 替换占位符（字符串操作，开销很小）
     - 处理消息列表（列表操作，开销很小）
   - **总体开销**：非常小（< 1ms），可以忽略

2. **模板加载**
   - 如果每次都需要重新加载模板，会有文件 I/O 开销
   - **优化方案**：模板可以缓存，或者从 Agent 创建时的系统消息中提取

### 3.3 兼容性影响

#### 向后兼容性

1. **API 接口**：无需修改
2. **配置文件**：无需修改
3. **提示词模板**：无需修改（占位符格式保持不变）

#### 潜在问题

1. **系统消息重复**
   - 如果 Agent 创建时已经注入了系统消息，运行时又注入，可能导致重复
   - **解决方案**：在运行时替换或移除 Agent 创建时的系统消息

2. **Checkpointer 兼容性**
   - 需要确保动态注入的系统消息能够正确持久化
   - **验证点**：多轮对话中系统消息是否正确保持

### 3.4 测试工作量

#### 需要测试的场景

1. **基础功能测试**
   - 验证占位符是否正确替换
   - 验证系统消息是否正确注入
   - 验证 Agent 功能是否正常

2. **边界情况测试**
   - state 中缺少某些字段时的处理
   - 占位符未定义时的处理
   - 系统消息格式错误时的处理

3. **多轮对话测试**
   - 验证系统消息在多轮对话中是否正确保持
   - 验证 checkpointer 机制是否正常

4. **性能测试**
   - 验证运行时开销是否可接受
   - 验证内存使用是否正常

**预估测试工作量**：2-3 天

## 四、改造好处分析

### 4.1 功能完整性

#### 解决的问题

1. **占位符替换完整**
   - ✅ 所有占位符都能正确替换（包括 `user_id`, `session_id`, `user_info`, `history_msg`）
   - ✅ 每个请求都能使用正确的上下文信息

2. **动态上下文支持**
   - ✅ 支持每个请求使用不同的上下文信息
   - ✅ 支持多用户、多会话场景

#### 功能增强

1. **更灵活的提示词管理**
   - 提示词模板可以在运行时动态调整
   - 可以根据不同的 state 生成不同的系统消息

2. **更好的可观测性**
   - 系统消息的内容可以在运行时记录和调试
   - 可以验证占位符替换是否正确

### 4.2 架构优势

#### 符合 LangGraph 设计模式

1. **消息驱动架构**
   - 系统消息作为消息列表的一部分，符合 LangGraph 的设计理念
   - 可以利用 LangGraph 的消息处理机制

2. **状态管理清晰**
   - 上下文信息从 state 中获取，状态管理清晰
   - 不依赖全局变量或单例模式

#### 代码可维护性

1. **职责分离**
   - Agent 创建：负责加载模板和创建 Agent 实例
   - 运行时注入：负责根据 state 动态生成系统消息
   - 职责清晰，易于维护

2. **扩展性好**
   - 可以轻松添加新的占位符
   - 可以支持更复杂的系统消息生成逻辑

### 4.3 开发体验

#### 调试友好

1. **运行时可见**
   - 可以在运行时查看完整的系统消息内容
   - 可以验证占位符替换是否正确

2. **错误定位容易**
   - 如果占位符替换失败，错误信息清晰
   - 可以快速定位问题

#### 开发效率

1. **提示词修改方便**
   - 修改提示词模板后，不需要重新创建 Agent
   - 可以在运行时动态调整（如果实现模板热加载）

2. **测试简单**
   - 可以轻松测试不同的 state 场景
   - 可以模拟各种边界情况

### 4.4 长期收益

#### 可扩展性

1. **支持更复杂的场景**
   - 可以根据用户类型、会话类型生成不同的系统消息
   - 可以支持 A/B 测试（不同的提示词版本）

2. **支持个性化**
   - 可以根据用户历史、偏好生成个性化的系统消息
   - 可以支持动态调整提示词策略

#### 技术债务减少

1. **解决根本问题**
   - 不再需要在 Agent 创建时处理运行时才能获取的数据
   - 架构更加合理

2. **为未来铺路**
   - 如果未来需要支持更复杂的提示词生成逻辑，架构已经支持
   - 可以轻松集成提示词版本管理、A/B 测试等功能

## 五、实施建议

### 5.1 实施步骤

1. **第一步：修改 Agent 创建逻辑**
   - 修改 `domain/agents/factory.py`
   - 只填充时间相关占位符，保留其他占位符标记
   - 测试 Agent 创建是否正常

2. **第二步：实现运行时系统消息注入**
   - 修改 `domain/router/graph.py` 的 `with_user_context` 函数
   - 实现占位符替换逻辑
   - 实现系统消息处理逻辑

3. **第三步：测试验证**
   - 单元测试：验证占位符替换逻辑
   - 集成测试：验证完整流程
   - 性能测试：验证运行时开销

4. **第四步：优化和文档**
   - 优化代码性能（如模板缓存）
   - 更新相关文档
   - 添加日志和监控

### 5.2 风险控制

1. **渐进式实施**
   - 可以先在一个 Agent 上实施，验证无误后再推广
   - 保留回滚方案

2. **充分测试**
   - 覆盖所有使用占位符的 Agent
   - 覆盖各种边界情况

3. **监控和告警**
   - 添加占位符替换失败的告警
   - 监控系统消息注入的成功率

### 5.3 推荐方案

**建议采用方案三（LangGraph 系统消息机制）**，原因：

1. ✅ **符合 LangGraph 设计模式**：利用系统消息机制，架构合理
2. ✅ **功能完整**：所有占位符都能正确替换
3. ✅ **性能影响小**：运行时开销可以忽略
4. ✅ **扩展性好**：为未来功能扩展打下基础
5. ✅ **代码可维护性强**：职责清晰，易于理解和维护

**相比方案一的优势**：
- 不需要修改 Agent 内部的系统消息（更安全）
- 系统消息和用户消息分离，逻辑更清晰
- 更符合 LangGraph 的设计理念

**相比方案二的优势**：
- 不需要修改 Agent 创建逻辑（保持缓存机制）
- 实现更简单，风险更小

## 六、总结

方案三（LangGraph 系统消息机制）是一个**架构合理、功能完整、风险可控**的解决方案。虽然需要一定的代码修改和测试工作，但带来的好处是长期的：

- ✅ 解决占位符替换问题
- ✅ 提升代码可维护性
- ✅ 为未来扩展打下基础
- ✅ 符合 LangGraph 最佳实践

**建议优先级**：高（推荐实施）

