# LangGraph Input 与 Output Schema 区分改造指南

## 文档说明

本文档讲解如何在当前项目中实现 **input schema** 与 **output schema** 的区分，使图的输入保持原有结构，而输出仅返回 API 所需字段（而非完整 FlowState）。

**文档版本**：V1.0  
**创建时间**：2025-02-02  
**关联文档**：`020203-LangGraph状态设计与FlowState方案合规性.md`

---

## 一、你的理解是否正确？

> 输入和原来一样，但是输出进行改造，不是当前的大的 state 的所有值。

**结论：理解正确。**

- **Input**：可以保持与 `build_initial_state` 构建的结构一致，或进一步精简为只含「对外必需」字段。
- **Output**：应改造为只返回 API 需要的字段（如 `flow_msgs`、`session_id` 等），而不是整个 FlowState（含 `prompt_vars`、`edges_var`、`persistence_edges_var` 等内部字段）。

这样做的价值：
1. **API 契约清晰**：调用方只看到需要的字段，避免暴露内部状态。
2. **Langfuse 等可观测性**：output 更精简，便于理解和排查。
3. **符合 LangGraph 官方推荐**：复杂图可拆 input/output schema，内部仍用完整 state。

---

## 二、LangGraph 的 input/output schema 机制

### 2.1 核心概念

LangGraph 的 `StateGraph` 支持三个 schema 参数：

| 参数 | 含义 | 默认行为 |
|------|------|----------|
| **state_schema**（第一个位置参数） | 图内部共享的完整状态 | 所有节点读/写此 schema |
| **input_schema** | 图对外的输入约束 | 未指定时 = state_schema |
| **output_schema** | 图对外的输出约束 | 未指定时 = state_schema，即返回完整 state |

当指定 `output_schema` 后，`invoke` / `ainvoke` 的返回值**只包含 output_schema 中定义的 key**，其余内部字段不会出现在返回值中。

### 2.2 官方示例（摘录）

```python
from typing_extensions import TypedDict

class InputState(TypedDict):
    user_input: str

class OutputState(TypedDict):
    graph_output: str

class OverallState(TypedDict):
    foo: str
    user_input: str
    graph_output: str

# 关键：StateGraph 初始化时传入 input_schema 和 output_schema
builder = StateGraph(
    OverallState,
    input_schema=InputState,
    output_schema=OutputState
)
# ... 添加节点和边 ...
graph = builder.compile()

# 调用时：输入只需符合 InputState
# 返回时：只包含 OutputState 的 key
result = graph.invoke({"user_input": "My"})
# result = {'graph_output': 'My name is Lance'}  # 只有 graph_output，没有 foo、user_input
```

要点：
- 内部节点仍读写 `OverallState` 的全部字段。
- 对外：输入只需 `user_input`，输出只有 `graph_output`。

---

## 三、当前项目实现分析

### 3.1 现状

| 环节 | 当前实现 | 说明 |
|------|----------|------|
| **输入** | `build_initial_state()` 构建完整 FlowState | 含 current_message、history_messages、flow_msgs、session_id、prompt_vars 等 |
| **图构建** | `StateGraph(FlowState)` | 未指定 input/output schema |
| **输出** | `graph.ainvoke(initial_state, config)` 返回完整 FlowState | 含所有内部字段 |
| **Chat 路由** | 从 `result` 中手动提取 `flow_msgs` | 实际只用 flow_msgs，其余字段被忽略 |

### 3.2 相关代码位置

- **状态定义**：`backend/domain/state.py` — `FlowState`
- **图构建**：`backend/domain/flows/builder.py` — `StateGraph(FlowState)`
- **图编译**：`backend/domain/flows/manager.py` — `graph.compile(checkpointer=checkpoint)`
- **Chat 路由**：`backend/app/api/routes/chat.py` — `result = await graph.ainvoke(...)`，然后从 `result` 取 `flow_msgs`

---

## 四、改造方案

### 4.1 定义 Input / Output Schema

在 `backend/domain/state.py` 中新增 TypedDict：

```python
from typing import TypedDict, List, Optional, Dict, Any, Annotated
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages


# ========== 对外 Input Schema ==========
# 图接收的输入：只包含调用方需要传入的字段
class FlowInputSchema(TypedDict, total=False):
    """图对外输入 schema"""
    current_message: HumanMessage
    history_messages: List[BaseMessage]
    flow_msgs: List[BaseMessage]  # 初始可为空
    session_id: str
    token_id: Optional[str]
    trace_id: Optional[str]
    prompt_vars: Optional[Dict[str, Any]]  # 若由 API 层构建，可保留


# ========== 对外 Output Schema ==========
# 图返回的输出：只包含 API 需要的字段
class FlowOutputSchema(TypedDict, total=False):
    """图对外输出 schema"""
    flow_msgs: List[BaseMessage]  # Chat 路由主要使用
    session_id: str              # 可选，便于链路追踪


# ========== 内部完整 State（保持不变）==========
class FlowState(TypedDict, total=False):
    """流程状态数据结构（内部完整 schema）"""
    current_message: HumanMessage
    history_messages: List[BaseMessage]
    flow_msgs: Annotated[List[BaseMessage], add_messages]
    session_id: str
    token_id: Optional[str]
    trace_id: Optional[str]
    prompt_vars: Optional[Dict[str, Any]]
    edges_var: Optional[Dict[str, Any]]
    persistence_edges_var: Optional[Dict[str, Any]]
```

### 4.2 修改图构建

在 `backend/domain/flows/builder.py` 中：

```python
from backend.domain.state import FlowState, FlowInputSchema, FlowOutputSchema

# 修改前
# graph = StateGraph(FlowState)

# 修改后
graph = StateGraph(
    FlowState,
    input_schema=FlowInputSchema,
    output_schema=FlowOutputSchema
)
```

### 4.3 输入保持不变

`build_initial_state` 返回的字典已经符合 `FlowInputSchema`（且是 FlowState 的子集），无需修改。调用方式不变：

```python
initial_state = build_initial_state(request, current_message, history_messages)
result = await graph.ainvoke(initial_state, config)
```

### 4.4 输出变化

改造后，`result` 的类型为 `FlowOutputSchema`，**只包含** `flow_msgs` 和 `session_id`（若在 output_schema 中定义）。  
`prompt_vars`、`edges_var`、`persistence_edges_var` 等内部字段**不会**出现在 `result` 中。

Chat 路由可简化为：

```python
# 改造前：result 是完整 FlowState，需手动提取
flow_msgs = result.get("flow_msgs", [])

# 改造后：result 已是 FlowOutputSchema，结构更清晰
flow_msgs = result.get("flow_msgs", [])  # 写法相同，但 result 已不包含内部字段
```

若 output_schema 只保留 `flow_msgs`，可进一步简化类型注解和文档。

---

## 五、改造步骤汇总

| 步骤 | 文件 | 操作 |
|------|------|------|
| 1 | `backend/domain/state.py` | 新增 `FlowInputSchema`、`FlowOutputSchema` |
| 2 | `backend/domain/flows/builder.py` | `StateGraph(FlowState, input_schema=..., output_schema=...)` |
| 3 | `backend/app/api/routes/chat.py` | 无需逻辑改动，仅 result 类型变化 |
| 4 | 测试 | 验证 ainvoke 返回值仅含 output_schema 字段 |

---

## 六、注意事项

### 6.1 output_schema 的 key 必须在 FlowState 中存在

`FlowOutputSchema` 中的 key（如 `flow_msgs`、`session_id`）必须是 `FlowState` 中已有的 key，否则框架无法从最终 state 中提取输出。

### 6.2 输入兼容性

`FlowInputSchema` 可以是 `FlowState` 的**子集**。未在 input_schema 中声明的 key，仍可由节点写入（如 `edges_var` 由路由节点写入），只要它们在 `FlowState` 中定义即可。

### 6.3 按需调整 output 字段

可根据实际 API 需求调整 `FlowOutputSchema`：
- 仅 `flow_msgs`：Chat 场景最常见。
- 加上 `session_id`：便于日志和追踪。
- 若未来有「返回意图」等需求，可增加对应字段。

---

## 七、总结

- **Input**：通过 `input_schema` 约束调用方传入的字段，当前 `build_initial_state` 已满足，可保持不变。
- **Output**：通过 `output_schema` 约束返回值，只暴露 `flow_msgs`（及少量追踪字段），不再返回完整 FlowState。
- **内部**：节点仍使用完整 `FlowState` 通信，无需改动节点逻辑。

这样即可实现「输入与原来一致，输出只返回必要字段」的改造目标。

---

## 八、改造完成情况

| 任务 | 状态 | 说明 |
|------|------|------|
| 在 state.py 中新增 FlowInputSchema、FlowOutputSchema | ✅ 已完成 | 已定义并导出 |
| 修改 builder.py 使用 input_schema 和 output_schema | ✅ 已完成 | `StateGraph(FlowState, input_schema=..., output_schema=...)` |
| chat.py 兼容性 | ✅ 无需改动 | `result.get("flow_msgs", [])` 写法不变，result 已自动过滤 |
| 单元测试 | ✅ 已完成 | `cursor_test/test_input_output_schema.py`，2 个用例通过 |

**测试命令**：
```bash
pytest cursor_test/test_input_output_schema.py -v
```

**改造完成时间**：2025-02-02

---

**文档生成时间**：2025-02-02  
**对应代码**：`backend/domain/state.py`、`backend/domain/flows/builder.py`、`backend/app/api/routes/chat.py`
