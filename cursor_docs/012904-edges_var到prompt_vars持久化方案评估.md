# edges_var 到 prompt_vars 持久化方案评估

## 1. 问题与根因

### 1.1 现象

- **optimization_agent**（flow.yaml 约 17–18 行）的输出会写入 `state.edges_var`（如 intent、confidence、scene_summary 等）。
- 这些数据需要传递到**下下个节点**（如 **blood_agent**，约 35–46 行）供提示词占位符使用。
- 实际效果：下游 agent 的 prompt 中拿不到这些变量，只能用于当步的边条件判断。

### 1.2 根因

1. **edges_var 的“临时性”**
   - 在 `agent_creator.py` 中，每个 agent 节点返回前都会执行：
     - `new_state["edges_var"] = {}`，再只写入**当前节点**的输出。
   - 因此 edges_var 的设计是「本节点产出、供边条件用」，不保证跨多步传递。

2. **中间节点覆盖**
   - 流程为：optimization_agent → **rag_node** → blood_agent。
   - `rag_agent_creator.py` 中（约 172–178 行）：
     - `new_state["edges_var"] = { "edges_prompt_vars": { ... } }` 是**整体赋值**。
   - 上一节点写入的 intent、confidence 等被完全覆盖，blood_agent 收到的 state 里已无这些字段。

3. **占位符来源**
   - `sys_prompt_builder.build_system_message` 只从两类来源取占位符：
     - `state.prompt_vars`（持久）
     - `state.edges_var["edges_prompt_vars"]`（当前/上一节点写入的临时结构）。
   - 既然后续 agent 会清空 edges_var、rag 又覆盖，optimization 的输出自然不会出现在 blood_agent 的 prompt 中。

结论：**edges_var 是“当步/边条件”语义，不是“跨多步、供下游 prompt 用”的通道；要实现后者，需要把需要持久化的字段写入 prompt_vars。**

---

## 2. 您提出的方案：config 驱动「部分 edges_var → prompt_vars」

### 2.1 思路

- 在 **flow.yaml** 的节点 config 中增加一个 **config key**（例如 `persist_to_prompt_vars`）。
- 当 **agent_creator** 遇到该 key 时，在**现有「输出 → edges_var」逻辑之后**，把 **edges_var** 中指定的 key 再**复制到 prompt_vars**。
- 这样：
  - 边条件仍用 edges_var（现有逻辑不变）。
  - 需要给下下个节点用的字段进入 prompt_vars，不再被 rag 覆盖，下游 agent 的 prompt 占位符可正常引用。

### 2.2 可行性结论：**可行且推荐**

- **语义清晰**：仅对“需要持久化到下游 prompt”的节点显式配置，不改变 edges_var 的通用语义。
- **改动集中**：只动 agent_creator + flow 配置，不动 rag、不动 state 结构。
- **兼容现有行为**：不配该 key 的节点行为与现在完全一致。
- **与现有架构一致**：prompt_vars 本来就是“供提示词占位符用”的持久存储，用来承载“上游 agent 需要给下游 prompt 用的字段”是合理用法。

### 2.3 实现要点

1. **Config 设计（建议）**
   - Key 名：如 `persist_to_prompt_vars`。
   - 值：建议为 **key 列表**，例如 `["intent", "confidence", "scene_summary", "optimization_question"]`，表示只把这些字段从 edges_var 同步到 prompt_vars。
   - 可选：支持 `true` 表示“当前节点写入 edges_var 的所有 key 都同步”（便于小流量或调试），默认更推荐显式列表，便于审计和可控。

2. **在 agent_creator 中的位置**
   - 在现有「从 output 解析 JSON → 写入 `new_state["edges_var"]`」的逻辑**之后**（即约 112–142 行之后）。
   - 读取 `node_def.config.get("persist_to_prompt_vars")`：
     - 若为列表：仅将列表中且存在于 `new_state["edges_var"]` 的 key 复制到 `new_state["prompt_vars"]`。
     - 若为 `True`：可将本节点写入的 edges_var 全量复制（按需实现）。
   - **prompt_vars 合并方式**：  
     - `new_state["prompt_vars"] = (state.get("prompt_vars") or {}).copy()`，再对要持久化的 key 做 `new_state["prompt_vars"][k] = new_state["edges_var"][k]`，避免覆盖已有 prompt_vars 中其它无关 key。

3. **flow.yaml 示例（optimization_agent）**

```yaml
- name: optimization_agent
  type: agent
  config:
    prompt: prompts/10-optimization-agent.md
    persist_to_prompt_vars:
      - intent
      - confidence
      - scene_summary
      - optimization_question
      # 按需增删
    model:
      provider: doubao
      ...
```

4. **注意**
   - 若 Pydantic 的 AgentNodeConfig 当前只校验 `prompt`、`model`、`tools`，config 是 `Dict[str, Any]`，新增 key 不会破坏解析；若将来对 config 做严格 schema，需在 AgentNodeConfig 中为 `persist_to_prompt_vars` 增加可选字段（如 `Optional[List[str]]`）。

---

## 3. 其它可选方案对比

### 3.1 方案 A：在 rag_node 中合并上游 edges_var（不推荐）

- 思路：rag 更新 state 时，不直接 `new_state["edges_var"] = { "edges_prompt_vars": {...} }`，而是先读取 `state.get("edges_var", {})`，保留与边条件/下游 prompt 相关的 key（如 intent、confidence），再与本次的 `edges_prompt_vars` 合并写回。
- 缺点：
  - 每个“中间节点”都要知道上游有哪些 key 需要透传，耦合高、易漏。
  - 语义混乱：rag 既管检索又管透传上游业务字段，职责不清晰。
- 结论：不推荐作为主方案。

### 3.2 方案 B：约定“某节点输出的全部/部分 key 自动进 prompt_vars”（无 config）

- 思路：例如约定“optimization_agent 节点的输出中，除 response_content/reasoning_summary 外，全部写入 prompt_vars”。
- 缺点：写死在代码里，不同流程、不同节点无法差异化；且可能把只适合边条件的临时字段也写入 prompt_vars，造成污染。
- 结论：不如“按 config 指定 key”灵活可控。

### 3.3 方案 C：显式“通道”字段（如 state.downstream_prompt_vars）

- 思路：在 state 中增加专门字段，例如 `downstream_prompt_vars`，仅用于“上一节点希望传给下游 prompt 的变量”；build_system_message 合并 prompt_vars 与 downstream_prompt_vars；每个 agent 返回前可清空或覆盖该通道。
- 对比：
  - 与“用现有 prompt_vars”相比，多了一个状态维度和一套合并逻辑，但“边条件用 edges_var、下游 prompt 用 X”的边界更显式。
  - 若希望严格区分“会话级 prompt_vars”和“本链路上游传来的 prompt 变量”，可采用；否则在现有架构下直接复用 prompt_vars 更简单。
- 结论：可选，但当前需求下“指定 key 写入 prompt_vars”足够且实现成本更低。

---

## 4. 工业界常见做法（简要）

- **DAG/工作流 state**：通常区分「仅本步/边条件用」与「需向下游传递」的变量；后者往往有单独命名或通道（如 payload、context、user_context），避免被中间节点覆盖。
- **LangGraph / LangChain**：state 多为 TypedDict 或类似结构，常见做法是：
  - 将“需要跨多步、供后续节点读”的字段放在持久槽位（如您项目中的 prompt_vars）；
  - 将“仅本步或边路由用”的放在临时槽位（如 edges_var）。
- **配置驱动**：通过 YAML/JSON 声明“本节点哪些输出要写入全局/下游上下文”，是常见且可维护的做法，与您提出的 config key 思路一致。

---

## 5. 总结与推荐

- **根本原因**：edges_var 被设计为临时、且被中间节点（rag）整体覆盖，导致 optimization_agent 的输出无法到达 blood_agent 的 prompt。
- **推荐方案**：采用您提出的方式——在 agent 节点 config 中增加 **persist_to_prompt_vars**（建议值为 key 列表），在 **agent_creator** 中在写入 edges_var 之后，把所列 key 从 edges_var 复制到 prompt_vars，并保证 prompt_vars 以合并方式更新、不破坏已有 key。
- **可选增强**：若未来有“仅本链路上游、非会话级”的强需求，可再考虑 state.downstream_prompt_vars 等显式通道；当前阶段用 prompt_vars 即可满足“传递到下下个节点供 prompt 使用”的需求。
