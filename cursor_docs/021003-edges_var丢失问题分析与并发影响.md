# edges_var 丢失问题分析与并发影响

## 一、问题现象

流程运行中，`update_rewritten_data_node` 有时读到 **state 中 `edges_var` 为空或无效**，导致：

- `state.get("edges_var") or {}` 得到空字典；
- `_has_valid_rewritten_data(edges_var)` 为 False；
- 走失败分支：`status = STATUS_FAILED`，`execution_metadata["failure_reason"] = "edges_var 中无有效改写结果"`。

相关代码位置：

- **读取与判断**：`backend/domain/flows/implementations/update_rewritten_data_func.py` 第 165–166 行、第 175–182 行。
- **并发执行**：`backend/pipeline/rewritten_service.py` 第 422–425 行（`asyncio.gather` 并行执行多条 `run_one_rewritten`）。

本文分析：是否由「不同线程/任务之间的数据串写」导致，以及更可能的原因与应对建议。

---

## 二、并发模型说明（重要：不是多线程）

当前后端是 **asyncio 协程并发**，不是多线程：

- `rewritten_worker_loop` 里用 `asyncio.gather(..., return_exceptions=True)` 并发执行多个 `run_with_semaphore(rec)`；
- 每个 `run_with_semaphore` 内部调用 `run_one_rewritten(rec)` → `_run_one(...)` → `graph.ainvoke(initial_state, config)`；
- 没有使用 `threading`，不存在「线程局部变量」或「多线程共享变量」的经典问题。

因此，若出现 state 异常，更可能是：**单次调用链内 state 未正确传递**，或 **上游节点未写入有效 edges_var**，而不是「不同线程互相覆盖内存」。

---

## 三、状态隔离机制（为何理论上不会「串任务」）

### 3.1 每次运行都有独立的 initial_state 和 config

- `_run_one` 中（`rewritten_service.py` 第 193–214 行）：
  - 每次为当前 `record` 生成新的 `trace_id`、`session_id = f"rewritten_{record_id}"`；
  - `initial_state = build_state_from_record(...)` 是**新构建的 dict**，不与其他任务共享；
  - `config = {"configurable": {"thread_id": session_id}}`，即 **thread_id = session_id**，且 `record_id` 为当前改写任务主键，不同任务 `thread_id` 不同。

### 3.2 图实例与 checkpointer

- `FlowManager.get_flow(FLOW_KEY)` 返回的是**同一流程的单例编译图**（`manager.py` 第 80–108 行），即多任务**共享同一个 graph 实例**；
- 图使用 `MemorySaver()` 作为 checkpointer（`manager.py` 第 124 行）；
- LangGraph 按 `config["configurable"]["thread_id"]` 隔离 checkpoint 状态，因此：
  - 任务 A：`thread_id = "rewritten_id_A"` → 读写 checkpoint_A；
  - 任务 B：`thread_id = "rewritten_id_B"` → 读写 checkpoint_B；
  - 理论上**不会出现「任务 A 的 state 被任务 B 覆盖」** 的跨任务串写。

### 3.3 小结

在现有实现下，**并发导致「不同任务之间」state/edges_var 互相覆盖** 的可能性较低。更应优先从「单次流程内 state 来源」和「上游节点是否写出有效数据」排查。

---

## 四、edges_var 的真实来源与「丢失」的合理解释

### 4.1 数据流

- **写入**：仅由 `rewritten_agent_node`（Agent 节点）在 `agent_creator.py` 中写入；
- **读取**：`update_rewritten_data_node` 从 `state.get("edges_var") or {}` 读取，并用 `_has_valid_rewritten_data(edges_var)` 判断是否有有效改写字段（如「场景描述」「患者提问」等）。

流程：`entry → rewritten_agent_node → update_rewritten_data_node → END`，中间无其他节点改写 `edges_var`。

### 4.2 agent_creator 中 edges_var 的写入逻辑（关键）

在 `backend/domain/flows/nodes/agent_creator.py` 第 102–141 行：

1. **先清空**：`new_state["edges_var"] = {}`（不继承上游，避免污染下游条件判断）。
2. **再填充**：仅当同时满足以下条件时才会往 `edges_var` 里写内容：
   - `result` 中有 `"output"`；
   - `output` 为字符串；
   - 能从 `output` 中截取到 `{ ... }` 并 `json.loads` 成功；
   - 解析结果为 dict，且键不在 `["response_content", "reasoning_summary", "additional_fields"]` 的会写入；若有 `additional_fields` 也会合并进去。
3. **解析失败时**：仅 `logger.debug("解析输出 JSON 失败...")`，**不抛异常**，流程继续，此时 **edges_var 保持为空字典**。

因此，以下情况都会导致下游看到「edges_var 无有效改写结果」：

- LLM 未返回 JSON，或返回格式无法被 `json.loads` 解析；
- LLM 返回的 JSON 中没有「场景描述」「患者提问」「回复案例」等业务字段，或这些字段均为空；
- `result` 中缺少 `"output"` 或 `output` 不是字符串。

这些都属于**单次运行内「上游未产出有效数据」**，与「多任务互相覆盖」无直接关系。

---

## 五、结论与建议

### 5.1 结论摘要

| 怀疑方向           | 结论 |
|--------------------|------|
| 多线程数据溢出/串写 | 当前为 asyncio，非多线程；且每任务独立 thread_id + 独立 initial_state，状态按 thread_id 隔离，**并发导致跨任务 state 串写可能性低**。 |
| edges_var 为空     | **更可能**是：rewritten_agent_node 未产出有效 JSON，或解析失败/字段不符合 `_has_valid_rewritten_data`，导致本任务内 edges_var 一直为空。 |

### 5.2 建议措施

1. **增强日志（优先）**
   - 在 `update_rewritten_data_func` 入口打日志：`trace_id`、`rewritten_record_id`、`list(state.get("edges_var") or {}.keys())`，便于确认是「本任务就没收到」还是「键名/键值不符合」。
   - 在 `agent_creator` 中，当 JSON 解析失败或未找到 `{`/`}` 时，将 `logger.debug` 提升为 `logger.warning`，并带上 `trace_id`/节点名，便于统计「多少比例是 LLM 未返回有效 JSON」。

2. **可选：persistence_edges_var 回退**
   - 若流程中为 `rewritten_agent_node` 配置了 `persist_to_persistence_edges_var`，可将改写结果同时写入 `persistence_edges_var`；
   - 在 `update_rewritten_data_func` 中，当 `edges_var` 无有效数据时，尝试从 `state.get("persistence_edges_var")` 按相同业务字段做一次回退读取（需与现有设计一致，避免重复更新逻辑）。

3. **排除并发（可选验证）**
   - 临时将 `MAX_CONCURRENT` 改为 1，或暂时改为「串行执行」（例如不启用 `asyncio.gather`，逐条 `await run_one_rewritten(rec)`）；
   - 若改为串行后「edges_var 中无有效改写结果」仍复现，则更能说明问题主要在上游产出或单次 state 传递，而非并发。

4. **提示词与输出格式**
   - 检查 `prompts/rewritten_agent.md`，确保明确要求 LLM 返回**单一 JSON 对象**，且包含「场景描述」「患者提问」等字段；
   - 必要时在 agent 输出后增加一层校验或重试（如非 JSON 时重试一次），减少「解析失败但流程继续」导致的静默空 edges_var。

---

## 六、相关代码索引

| 位置 | 说明 |
|------|------|
| `backend/pipeline/rewritten_service.py` 第 375–425 行 | Worker 循环；`asyncio.gather` 并发执行 `run_with_semaphore(rec)` |
| `backend/pipeline/rewritten_service.py` 第 185–221 行 | `_run_one`：构建 initial_state、config，调用 `graph.ainvoke` |
| `backend/domain/flows/implementations/update_rewritten_data_func.py` 第 165–182 行 | 读取 `edges_var`、判断有效改写、写失败元数据 |
| `backend/domain/flows/nodes/agent_creator.py` 第 102–141 行 | 清空并仅从 Agent 输出 JSON 填充 `edges_var` |
| `backend/domain/flows/manager.py` 第 80–128 行 | 单例图 + MemorySaver checkpointer |
| `config/flows/pipeline_step2/flow.yaml` | rewritten_agent_node → update_rewritten_data_node 边定义 |

---

*文档编号：021003；与 021001（批量异步执行技术设计）、021002（update_rewritten_data 链路与设计问题）配套。*
