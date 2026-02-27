# 当前Agent的整体流程现状

## 一、聊天接口请求流程

### 1.1 接口入口

**文件位置**：`app/api/routes.py`

**接口**：`POST /chat`

**请求处理流程**：

1. **接收请求**：接收 `ChatRequest`，包含：
   - `message`: 用户消息
   - `session_id`: 会话ID
   - `user_id`: 用户ID
   - `conversation_history`: 对话历史（可选）
   - `user_info`: 患者基础信息（可选）
   - `current_date`: 当前日期时间（可选）

2. **构建消息列表**：
   - 将 `conversation_history` 转换为 `HumanMessage` 和 `AIMessage`
   - 添加当前用户消息为 `HumanMessage`

3. **构建初始状态**（`RouterState`）：
   ```python
   {
       "messages": messages,
       "current_intent": None,
       "current_agent": None,
       "need_reroute": True,
       "session_id": request.session_id,
       "user_id": request.user_id,
       "trace_id": trace_id,
       "user_info": request.user_info or "暂无患者基础信息",
       "history_msg": history_msg,  # 格式化的历史对话文本
       "current_date": request.current_date
   }
   ```

4. **执行路由图**：
   - 调用 `router_graph.astream(initial_state, config)`
   - 配置中包含 `thread_id`（使用 `session_id`）

5. **提取响应**：
   - 从最终状态中提取最后一条 `AIMessage` 的内容
   - 返回 `ChatResponse`，包含：
     - `response`: 助手回复
     - `session_id`: 会话ID
     - `intent`: 识别的意图
     - `agent`: 使用的Agent名称

---

## 二、路由图结构

### 2.1 路由图构建

**文件位置**：`domain/router/graph.py`

**构建函数**：`create_router_graph()`

**路由图结构**：

```
┌─────────────────────────────────────────────────────────┐
│                    路由图（Router Graph）                 │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────┐                                            │
│  │  route  │  ← 入口节点（Entry Point）                  │
│  └────┬─────┘                                            │
│       │                                                  │
│       │ 条件路由（Conditional Edge）                     │
│       ├──────────────────────────────────────┐          │
│       │                                      │          │
│       ▼                                      ▼          │
│  ┌──────────────┐                    ┌──────────────┐  │
│  │clarify_intent│                    │Agent节点     │  │
│  └──────┬───────┘                    └──────┬───────┘  │
│         │                                    │          │
│         │ 回边（Edge）                       │ 回边     │
│         └────────────────────────────────────┘          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 2.2 节点类型

#### 2.2.1 路由节点（route）

**节点名称**：`route`

**实现函数**：`route_node()`（`domain/router/node.py`）

**功能**：
1. **防止无限循环**：检查最后一条消息是否为 `AIMessage`，如果是则停止执行
2. **意图识别**：调用 `identify_intent` 工具识别用户意图
3. **意图变化检测**：检测意图是否发生变化
4. **路由决策**：根据意图设置 `current_agent` 和 `need_reroute`

**使用的工具**：
- `identify_intent`: 意图识别工具（LLM调用）

**路由决策逻辑**：
- 如果 `need_reroute=False` 且 `current_agent` 存在 → 返回 `END`
- 如果 `need_reroute=True` 且意图为 `unclear` → 路由到 `clarify_intent`
- 如果 `current_agent` 存在 → 路由到对应的Agent节点
- 如果 `current_intent` 存在且匹配 → 路由到对应的Agent节点
- 否则 → 返回 `END`

#### 2.2.2 澄清节点（clarify_intent）

**节点名称**：`clarify_intent`

**实现函数**：`clarify_intent_node()`（`domain/router/node.py`）

**功能**：
1. 当意图不明确时，生成澄清问题
2. 将澄清问题作为 `AIMessage` 添加到消息列表
3. 设置 `need_reroute=True`，触发重新路由

**使用的工具**：
- `clarify_intent`: 意图澄清工具（LLM调用）

**执行后**：返回 `route` 节点（回边）

#### 2.2.3 Agent节点（动态创建）

**节点创建**：在 `create_router_graph()` 中动态创建

**创建流程**：
1. 从 `AgentRegistry` 获取所有Agent配置
2. 对每个Agent：
   - 通过 `AgentFactory.create_agent()` 创建Agent实例
   - 获取节点名称（从配置的 `routing.node_name` 获取）
   - 使用 `with_user_context()` 包装Agent节点
   - 添加到路由图

**当前Agent节点**（从 `config/agents.yaml` 加载）：

| Agent键名 | 节点名称 | 意图类型 | 说明 |
|----------|---------|---------|------|
| `blood_pressure_agent` | `blood_pressure_agent` | `blood_pressure` | 血压记录智能体 |
| `health_event_agent` | `health_event_agent` | `health_event` | 健康事件记录智能体 |
| `medication_agent` | `medication_agent` | `medication` | 用药记录智能体 |
| `symptom_agent` | `symptom_agent` | `symptom` | 症状记录智能体 |

**Agent节点包装**（`with_user_context`）：
1. 从 `state` 中获取占位符值
2. 加载Agent提示词模板（包含占位符）
3. 填充占位符，生成完整的系统提示词
4. 创建 `SystemMessage` 并插入到消息列表开头
5. 调用Agent执行
6. 保留路由状态中的关键字段（`session_id`、`user_id`、`current_intent`、`current_agent`、`need_reroute`、`trace_id`）

**执行后**：返回 `route` 节点（回边）

---

## 三、每个路由节点的工具使用情况

### 3.1 路由节点（route）

**使用的工具**：

| 工具名称 | 工具类型 | 状态 | 说明 |
|---------|---------|------|------|
| `identify_intent` | 路由工具 | ✅ 启用 | 意图识别工具，使用LLM识别用户意图 |

**工具详情**：
- **文件位置**：`domain/router/tools/router_tools.py`
- **功能**：识别用户意图（`blood_pressure`、`health_event`、`medication`、`symptom`、`unclear`）
- **提示词来源**：从Langfuse或本地文件加载（`router_intent_identification_prompt`）
- **返回结果**：`IntentResult`，包含：
  - `intent_type`: 意图类型
  - `confidence`: 置信度（0.0-1.0）
  - `entities`: 提取的实体信息
  - `need_clarification`: 是否需要澄清
  - `reasoning`: 识别理由

### 3.2 澄清节点（clarify_intent）

**使用的工具**：

| 工具名称 | 工具类型 | 状态 | 说明 |
|---------|---------|------|------|
| `clarify_intent` | 路由工具 | ✅ 启用 | 意图澄清工具，生成澄清问题 |

**工具详情**：
- **文件位置**：`domain/router/tools/router_tools.py`
- **功能**：当意图不明确时，生成友好的澄清问题
- **提示词来源**：从Langfuse或本地文件加载（`router_clarify_intent_prompt`）
- **返回结果**：澄清问题文本（字符串）

### 3.3 Agent节点工具使用情况

#### 3.3.1 血压记录智能体（blood_pressure_agent）

**节点名称**：`blood_pressure_agent`

**使用的工具**：

| 工具名称 | 工具类型 | 状态 | 说明 |
|---------|---------|------|------|
| `record_blood_pressure` | 业务工具 | ✅ 启用 | 记录血压数据 |
| `query_blood_pressure` | 业务工具 | ❌ **已停用** | 查询血压数据（已注释） |
| `update_blood_pressure` | 业务工具 | ❌ **已停用** | 更新血压数据（已注释） |

**停用原因**（根据 `config/agents.yaml` 注释）：
> 根据新的业务逻辑，历史数据由系统自动提供，Agent不需要主动查询。如需恢复，取消注释即可（同时需要更新提示词和确保系统提供历史数据的机制）

**工具详情**：
- **文件位置**：`domain/tools/blood_pressure/`
- **record_blood_pressure**：
  - 功能：记录血压数据到数据库
  - 参数：`user_id`、`systolic`、`diastolic`、`heart_rate`（可选）、`record_time`（可选）、`notes`（可选）
  - 返回：操作结果文本

#### 3.3.2 健康事件记录智能体（health_event_agent）

**节点名称**：`health_event_agent`

**使用的工具**：

| 工具名称 | 工具类型 | 状态 | 说明 |
|---------|---------|------|------|
| `record_health_event` | 业务工具 | ✅ 启用 | 记录健康事件 |
| `query_health_event` | 业务工具 | ✅ 启用 | 查询健康事件 |
| `update_health_event` | 业务工具 | ✅ 启用 | 更新健康事件 |

**工具详情**：
- **文件位置**：`domain/tools/health_event/`
- **record_health_event**：记录健康事件到数据库
- **query_health_event**：查询健康事件数据
- **update_health_event**：更新健康事件数据

#### 3.3.3 用药记录智能体（medication_agent）

**节点名称**：`medication_agent`

**使用的工具**：

| 工具名称 | 工具类型 | 状态 | 说明 |
|---------|---------|------|------|
| `record_medication` | 业务工具 | ✅ 启用 | 记录用药数据 |
| `query_medication` | 业务工具 | ✅ 启用 | 查询用药数据 |
| `update_medication` | 业务工具 | ✅ 启用 | 更新用药数据 |

**工具详情**：
- **文件位置**：`domain/tools/medication/`
- **record_medication**：记录用药数据到数据库
- **query_medication**：查询用药数据
- **update_medication**：更新用药数据

#### 3.3.4 症状记录智能体（symptom_agent）

**节点名称**：`symptom_agent`

**使用的工具**：

| 工具名称 | 工具类型 | 状态 | 说明 |
|---------|---------|------|------|
| `record_symptom` | 业务工具 | ✅ 启用 | 记录症状数据 |
| `query_symptom` | 业务工具 | ✅ 启用 | 查询症状数据 |
| `update_symptom` | 业务工具 | ✅ 启用 | 更新症状数据 |

**工具详情**：
- **文件位置**：`domain/tools/symptom/`
- **record_symptom**：记录症状数据到数据库
- **query_symptom**：查询症状数据
- **update_symptom**：更新症状数据

---

## 四、完整执行流程示例

### 4.1 新用户请求（意图明确）

```
1. 用户发送消息："我想记录血压，今天120/80"
   ↓
2. 路由图执行：
   route节点 → identify_intent工具 → 识别意图为"blood_pressure"
   ↓
3. 路由决策：
   current_intent = "blood_pressure"
   current_agent = "blood_pressure_agent"
   need_reroute = True
   ↓
4. 路由到Agent节点：
   blood_pressure_agent节点执行
   - 加载提示词模板并填充占位符
   - 创建SystemMessage
   - Agent执行（ReAct模式）
   - 调用record_blood_pressure工具
   - 生成回复
   ↓
5. 返回route节点：
   need_reroute = False（如果意图未变化）
   ↓
6. 路由决策：
   检测到need_reroute=False，返回END
   ↓
7. 提取响应：
   返回Agent生成的回复
```

### 4.2 意图不明确的情况

```
1. 用户发送消息："你好"
   ↓
2. 路由图执行：
   route节点 → identify_intent工具 → 识别意图为"unclear"
   ↓
3. 路由决策：
   current_intent = "unclear"
   need_reroute = True
   ↓
4. 路由到澄清节点：
   clarify_intent节点执行
   - 调用clarify_intent工具
   - 生成澄清问题
   - 添加AIMessage到消息列表
   ↓
5. 返回route节点：
   need_reroute = True
   ↓
6. 路由决策：
   检测到意图为unclear，再次路由到clarify_intent（如果用户没有新输入）
   或等待用户新输入后重新识别意图
```

### 4.3 多轮对话（同一意图）

```
1. 用户发送消息："我想记录血压"
   ↓
2. route节点 → 识别意图为"blood_pressure" → 路由到blood_pressure_agent
   ↓
3. Agent执行，询问："请告诉我您的血压值"
   ↓
4. 用户发送消息："120/80"
   ↓
5. route节点 → 识别意图为"blood_pressure"（意图未变化）
   ↓
6. 路由决策：
   - 检测到新的用户输入（has_new_user_input = True）
   - 强制设置need_reroute = True
   ↓
7. 路由到blood_pressure_agent（继续当前流程）
   ↓
8. Agent执行，调用record_blood_pressure工具，生成回复
```

---

## 五、关键配置说明

### 5.1 Agent配置（config/agents.yaml）

**配置项**：
- `name`: Agent名称
- `description`: Agent描述
- `llm`: LLM配置（`model`、`temperature`）
- `tools`: 工具列表（从 `TOOL_REGISTRY` 获取）
- `langfuse_template`: Langfuse提示词模板名称
- `placeholders`: Agent特定占位符配置
- `routing`: 路由配置
  - `node_name`: 路由图中的节点名称
  - `intent_type`: 对应的意图类型

### 5.2 工具注册表（domain/tools/registry.py）

**工具注册**：
- 所有工具在模块加载时自动注册到 `TOOL_REGISTRY`
- Agent创建时从注册表获取工具

**已注册的工具**：
- 血压工具：`record_blood_pressure`、`query_blood_pressure`（已停用）、`update_blood_pressure`（已停用）
- 健康事件工具：`record_health_event`、`query_health_event`、`update_health_event`
- 用药工具：`record_medication`、`query_medication`、`update_medication`
- 症状工具：`record_symptom`、`query_symptom`、`update_symptom`

### 5.3 路由状态（RouterState）

**状态字段**：
- `messages`: 消息列表（`List[BaseMessage]`）
- `current_intent`: 当前意图（`Optional[str]`）
- `current_agent`: 当前Agent（`Optional[str]`）
- `need_reroute`: 是否需要重新路由（`bool`）
- `session_id`: 会话ID（`str`）
- `user_id`: 用户ID（`str`）
- `trace_id`: Langfuse Trace ID（`Optional[str]`）
- `user_info`: 患者基础信息（`Optional[str]`）
- `history_msg`: 历史对话信息（`Optional[str]`）
- `current_date`: 当前日期时间（`Optional[str]`）

---

## 六、总结

### 6.1 当前流程特点

1. **动态路由**：根据意图动态路由到对应的Agent节点
2. **意图识别**：使用LLM进行智能意图识别
3. **意图澄清**：当意图不明确时，生成澄清问题
4. **多轮对话支持**：通过 `need_reroute` 和 `current_agent` 管理多轮对话
5. **工具动态加载**：Agent工具从配置文件动态加载
6. **提示词动态注入**：系统提示词在运行时动态注入，支持占位符填充

### 6.2 当前流程的节点和工具统计

**节点总数**：6个
- 路由节点：1个（`route`）
- 澄清节点：1个（`clarify_intent`）
- Agent节点：4个（`blood_pressure_agent`、`health_event_agent`、`medication_agent`、`symptom_agent`）

**工具总数**：14个
- 路由工具：2个（`identify_intent`、`clarify_intent`）
- 业务工具：12个
  - 启用：9个
  - 已停用：3个（`query_blood_pressure`、`update_blood_pressure`，以及可能的其他工具）

### 6.3 潜在问题和改进点

1. **工具停用不一致**：只有血压Agent停用了查询和更新工具，其他Agent仍保留
2. **路由逻辑复杂**：`route_node` 中的路由决策逻辑较复杂，包含多种条件判断
3. **回边设计**：所有Agent节点执行后都返回 `route` 节点，可能导致不必要的重新路由
4. **意图识别依赖LLM**：每次请求都需要调用LLM进行意图识别，可能影响性能

---

**文档生成时间**：2025-01-XX  
**基于代码版本**：当前代码库状态

