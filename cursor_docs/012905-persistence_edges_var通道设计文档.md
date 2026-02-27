# persistence_edges_var 通道设计文档

## 1. 背景与目标

### 1.1 问题

- 当前 **edges_var** 为「当步/边条件」语义：每个 agent 节点返回前会清空并只写入本节点输出，中间节点（如 rag_node）也可能整体覆盖 `edges_var`。
- 因此上游 agent（如 optimization_agent）写入的 intent、confidence 等无法透传到「下下个节点」，既无法参与后续边条件判断，也无法被更下游节点使用。

### 1.2 目标

- 新增**持久化通道** **persistence_edges_var**：
  - 生命周期与 **prompt_vars** 一致：一直存在，只在被显式写入时覆盖对应 key，**不会在传递过程中被清空或整体覆盖而消亡**。
  - 可透传到**任意下级节点**（包括跨多步），用于边条件判断及下游逻辑读取。
- 与 **prompt_vars** 区分含义：prompt_vars 面向「提示词占位符」等会话级/业务级变量；persistence_edges_var 面向「边条件 + 跨节点透传」的键值，语义更清晰。

### 1.3 方案概要

1. **FlowState** 新增字段 `persistence_edges_var: Optional[Dict[str, Any]]`。
2. **流程配置**：在需要透传的 agent 节点 config 中增加 **persist_to_persistence_edges_var**（列表），列出要从本节点 **edges_var** 同步到 **persistence_edges_var** 的 key。
3. **agent_creator**：在现有「输出 → edges_var」逻辑之后，按 config 将 **edges_var** 中指定 key **覆盖写入** **persistence_edges_var**（仅更新这些 key，不清空整个 persistence_edges_var）。
4. **边条件评估**：从 **persistence_edges_var** 与 **edges_var** 合并取值参与条件判断，**edges_var 优先级更高**。

---

## 2. 状态设计

### 2.1 FlowState 新增字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| **persistence_edges_var** | Optional[Dict[str, Any]] | 持久化边变量通道。与 prompt_vars 同生命周期：仅在被写入时覆盖对应 key，不在节点间传递时被清空。用于边条件及下游节点读取。 |

### 2.2 与现有字段的关系

| 字段 | 生命周期 | 主要用途 |
|------|----------|----------|
| **edges_var** | 当步/临时，每 agent 步清空后只写本节点输出，中间节点可能整体覆盖 | 当前步边条件、当前节点输出 |
| **persistence_edges_var** | 持久，仅按 key 覆盖，不整体清空 | 跨多步边条件、透传到任意下级节点 |
| **prompt_vars** | 持久，仅按 key 覆盖 | 提示词占位符、会话级/业务级变量 |

### 2.3 修改文件

- **backend/domain/state.py**：在 `FlowState` 中增加 `persistence_edges_var: Optional[Dict[str, Any]]`。

---

## 3. 配置设计

### 3.1 配置项

- **Key**：`persist_to_persistence_edges_var`
- **位置**：flow 中 agent 节点的 `config` 下（与 `prompt`、`model`、`tools` 同级）。
- **取值**：**列表**，元素为字符串，表示要从本节点 **edges_var** 同步到 **persistence_edges_var** 的 key。
- **可选**：不配置或配置为空列表时，不执行任何同步，行为与现有一致。

### 3.2 flow.yaml 示例

```yaml
- name: optimization_agent
  type: agent
  config:
    prompt: prompts/10-optimization-agent.md
    persist_to_persistence_edges_var:
      - intent
      - confidence
    model:
      provider: doubao
      temperature: 0.7
      thinking:
        type: disabled
```

### 3.3 配置校验（可选）

- 若使用 Pydantic 严格校验节点 config，需在 **AgentNodeConfig**（或等价模型）中为 `persist_to_persistence_edges_var` 增加可选字段，例如：  
  `persist_to_persistence_edges_var: Optional[List[str]] = None`。  
- 当前若 config 为 `Dict[str, Any]`，可不改模型，仅在 agent_creator 中 `config.get("persist_to_persistence_edges_var")` 读取即可。

---

## 4. agent_creator 逻辑

### 4.1 插入位置

在 **backend/domain/flows/nodes/agent_creator.py** 中，紧接在「通用化数据提取：输出 → edges_var」（约 112–142 行）**之后**、在「将 AI 回复存放到 flow_msgs」**之前**，增加「按 config 将 edges_var 指定 key 覆盖到 persistence_edges_var」的逻辑。

### 4.2 行为说明

- 读取 `node_def.config.get("persist_to_persistence_edges_var")`。
- 若不存在或非列表或为空列表：跳过，不修改 `persistence_edges_var`。
- 若为列表：
  - 取 `new_state["persistence_edges_var"] = (state.get("persistence_edges_var") or {}).copy()`，保证继承已有持久化变量（若当前 state 尚无该 key，则视为 `{}`）。
  - 对列表中每个 key `k`：若 `k` 存在于 `new_state["edges_var"]`，则执行  
    `new_state["persistence_edges_var"][k] = new_state["edges_var"][k]`。  
    即：**仅用本节点 edges_var 的值覆盖 persistence_edges_var 中同名字段**，其它 key 不动。
- 无需清空 `persistence_edges_var`：与 edges_var 不同，本通道采用「按 key 覆盖」，不整体重置。

### 4.3 伪代码

```text
# 在「从输出提取数据到 edges_var」逻辑之后
persist_keys = config_dict.get("persist_to_persistence_edges_var")
if isinstance(persist_keys, list) and len(persist_keys) > 0:
    if "persistence_edges_var" not in new_state or new_state["persistence_edges_var"] is None:
        new_state["persistence_edges_var"] = (state.get("persistence_edges_var") or {}).copy()
    else:
        # 确保是拷贝，避免修改到上游 state
        new_state["persistence_edges_var"] = (new_state.get("persistence_edges_var") or {}).copy()
    for k in persist_keys:
        if k in new_state["edges_var"]:
            new_state["persistence_edges_var"][k] = new_state["edges_var"][k]
    logger.debug("[节点 %s] 将 edges_var 的 key 同步到 persistence_edges_var: %s", node_name, persist_keys)
```

### 4.4 修改文件

- **backend/domain/flows/nodes/agent_creator.py**：在 `create()` 内构造的 `agent_node_action` 中，在 112–142 段逻辑后追加上述逻辑；注意 `node_def` 需在闭包中可用（当前已有 `node_name`，可同样通过闭包读取 `config_dict` 或 `node_def.config`）。

---

## 5. 边条件判断逻辑

### 5.1 需求

- 边条件表达式中使用的变量同时来自：
  - **persistence_edges_var**：历史节点写入的持久化边变量；
  - **edges_var**：当前/上一节点写入的临时边变量。
- 合并规则：**同一 key 以 edges_var 为准**（edges_var 优先级更高）。

### 5.2 实现位置

- **backend/domain/flows/condition_evaluator.py** 中的 **\_build_names_dict(state)**。

### 5.3 合并规则

1. 先取 `persistence_edges_var = state.get("persistence_edges_var") or {}`，复制为 `names` 的初始值（或先复制到 `names`）。
2. 再取 `edges_var = state.get("edges_var") or {}`，对 `edges_var` 中每个 key 执行 `names[k] = edges_var[k]`，实现「edges_var 覆盖 persistence_edges_var 同名字段」。
3. 后续 None 值处理等逻辑保持不变（对合并后的 `names` 做原有默认值处理）。

### 5.4 文档与注释

- 在 **ConditionEvaluator** 的 docstring 或 **\_build_names_dict** 的注释中说明：  
  变量来源为 **persistence_edges_var** 与 **edges_var** 的合并，**edges_var 优先级更高**。

### 5.5 修改文件

- **backend/domain/flows/condition_evaluator.py**：修改 `_build_names_dict`，先基于 `persistence_edges_var` 构建 `names`，再用 `edges_var` 覆盖同名 key；保留原有 None 默认值处理逻辑。

---

## 6. 生命周期与其它节点

### 6.1 persistence_edges_var 生命周期

- **创建**：首次有节点写入时出现（例如 agent 配置了 `persist_to_persistence_edges_var` 并成功写入）。
- **传递**：随 state 一起传递，**不会被任意节点整体清空**（与 edges_var 每步清空不同）。
- **更新**：仅当某节点显式写入某 key 时，该 key 被覆盖；未写入的 key 保持不变。
- **与 prompt_vars 一致**：仅「按 key 覆盖」，不在传递中消亡。

### 6.2 其它节点（如 rag、function 节点）

- 若未来需要由 **rag_node** 或 **function 节点** 写入 persistence_edges_var，可在对应节点的 creator 或实现中，在更新 state 时对 `new_state["persistence_edges_var"]` 按 key 进行写入（同样采用「先继承再按 key 覆盖」）。
- 本设计文档不强制修改 rag/function 节点；当前仅 **agent 节点** 通过 **persist_to_persistence_edges_var** 配置写入。

### 6.3 下游 prompt 占位符（可选扩展）

- 若希望下游 agent 的**提示词占位符**也能使用 persistence_edges_var 中的变量，可在 **build_system_message** 中增加对 `state["persistence_edges_var"]` 的合并（例如与 prompt_vars、edges_var["edges_prompt_vars"] 一起参与替换，并约定优先级）。  
- 当前设计**不包含**该扩展，仅保证边条件可从 persistence_edges_var + edges_var 合并取值。

---

## 7. 实现清单

| 序号 | 文件 | 改动摘要 |
|------|------|----------|
| 1 | backend/domain/state.py | FlowState 新增 `persistence_edges_var: Optional[Dict[str, Any]]` |
| 2 | backend/domain/flows/nodes/agent_creator.py | 在「输出 → edges_var」逻辑后，按 config `persist_to_persistence_edges_var` 将指定 key 从 edges_var 覆盖到 persistence_edges_var |
| 3 | backend/domain/flows/condition_evaluator.py | `_build_names_dict` 先取 persistence_edges_var，再以 edges_var 覆盖同名 key，再保留原有 None 默认值处理 |
| 4 | config/flows/medical_agent_v6_3/flow.yaml | 为 optimization_agent 的 config 增加 `persist_to_persistence_edges_var` 列表（按需填写 key） |

---

## 8. 测试建议

- **单元/集成**：构造 state 含 persistence_edges_var 与 edges_var，验证 ConditionEvaluator 合并后同名 key 以 edges_var 为准。
- **流程**：运行 medical_agent_v6_3，从 optimization_agent 经 rag_node 到 blood_agent 的边条件使用 intent、confidence 等，验证条件能正确取到 optimization_agent 写入的持久化值。
- **兼容**：不配置 `persist_to_persistence_edges_var` 的 agent 节点，行为与改动前一致；未设置 persistence_edges_var 的 state，边条件行为与仅使用 edges_var 时一致。

---

## 9. 完成情况

| 序号 | 文件/项 | 状态 | 说明 |
|------|---------|------|------|
| 1 | backend/domain/state.py | 已完成 | FlowState 新增 `persistence_edges_var: Optional[Dict[str, Any]]` |
| 2 | backend/domain/flows/nodes/agent_creator.py | 已完成 | 在「输出 → edges_var」逻辑后，按 config `persist_to_persistence_edges_var` 将指定 key 从 edges_var 覆盖到 persistence_edges_var |
| 3 | backend/domain/flows/condition_evaluator.py | 已完成 | `_build_names_dict` 先取 persistence_edges_var，再以 edges_var 覆盖同名 key，保留原有 None 默认值处理；docstring 已更新 |
| 4 | config/flows/medical_agent_v6_3/flow.yaml | 已完成 | optimization_agent 增加 `persist_to_persistence_edges_var: [intent, confidence, scene_summary, optimization_question]` |
| 5 | cursor_test/test_condition_evaluator_persistence_edges_var.py | 已完成 | 5 个用例：仅 persistence_edges_var、仅 edges_var、合并且 edges_var 优先、edges_var 部分覆盖、空 state；运行 `pytest cursor_test/test_condition_evaluator_persistence_edges_var.py -v` 全部通过 |
