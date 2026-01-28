# create_rag_data 脚本 Langfuse 对接迭代方案

## 1. 背景与目标

- **现状**：`scripts/create_rag_data/run_create_rag_data.py` 当前在调用单节点 flow（create_rag_agent）时**未对接 Langfuse**，即未传入 `trace_id`、`callbacks`（Langfuse CallbackHandler）、也未使用 `RuntimeContext`，导致脚本触发的 LLM 调用无法在 Langfuse 中形成 Trace/Span。
- **目标**：为脚本触发的每次「单文件 → flow.ainvoke」建立可观测链路，与项目内其他流程（如 API 聊天、embedding 导入）一致，便于在 Langfuse 中按 trace/session 查看调用、耗时与错误。
- **参考实现**：项目内与「脚本直接调用 graph.ainvoke」最接近的是 **embedding 导入**：`scripts/embedding_import/run_embedding_import_parallel.py` + `scripts/embedding_import/core/runner.py`。该实现**并未**把脚本逻辑封装成 flow 的 function 节点，而是在**脚本侧**对每一次 `graph.ainvoke` 做三件事：生成 `trace_id`/`session_id`、创建 `create_langfuse_handler(context={"trace_id": trace_id})` 并传入 `config["callbacks"]`、在 `RuntimeContext(token_id, session_id, trace_id)` 下执行 ainvoke。

## 2. 方案对比与推荐

### 2.1 方案一：脚本侧直接对接 Langfuse（推荐）

**思路**：不改 flow 结构，仅在脚本与 `flow_runner` 中补齐 Langfuse 所需的三要素，与 embedding_import 的 runner 保持一致。

| 要素 | 做法 |
|------|------|
| trace_id | 每个文件处理时生成唯一 trace_id（如 `secrets.token_hex(16)`），并写入 state 的 `trace_id` 字段（若框架会读）且传入 handler context。 |
| callbacks | 调用 `create_langfuse_handler(context={"trace_id": trace_id})`，将返回的 handler 放入 `config["callbacks"]`，再传给 `graph.ainvoke(initial_state, config)`。 |
| RuntimeContext | 在 ainvoke 前进入 `with RuntimeContext(token_id=..., session_id=..., trace_id=...)`，保证工具/下游可读到 session_id、trace_id。 |

**优点**：改动小、不引入新 flow 节点、行为与现有 embedding 导入脚本一致，Langfuse 上「一个文件一条 trace」清晰。  
**缺点**：脚本仍是「外层调度」，flow 内仅单 agent 节点，不体现「整批任务」为一条父 trace（若需整批一条 trace，可在方案一基础上再包一层 trace，见下文可选增强）。

**结论**：优先采用方案一；无需将脚本逻辑封装成 flow 的 function 节点即可完成 Langfuse 对接。

### 2.2 方案二：流程内 function 节点封装脚本逻辑

**思路**：将「获取文件列表 → 读文件 → 调 LLM（或子图）→ 解析 → 落库」整段逻辑封装成**一个 function 节点**，由 flow 编排；脚本只负责启动该 flow 并传入参数（如文件路径列表或目录）。Langfuse 可在该 function 节点内创建 trace/observation，或由 flow 的 entry 先建 trace，再进入 function 节点。

**与 rag_source_agent 的 function 节点对比**：  
`config/flows/rag_source_agent/flow.yaml` 中的 `format_data_node`（约 20–21 行）是 `type: function`、`function_key: "before_embedding_func"`，其职责是**从 state 读上一节点输出、加工后写回 state**，不负责「批量调度多文件、多次调 LLM」。若要把 create_rag_data 的**整段脚本逻辑**放进 function 节点，则需要：

- 新增一个 function 实现（如 `create_rag_data_batch_func`）：入参来自 state（如文件路径列表或目录），内部循环：读文件 → 调 create_rag_agent 子图或直接调 LLM → 解析 → 落库；并在该函数内创建 Langfuse trace/observation（或使用项目提供的 handler/trace 接口）。
- flow 需至少包含：一个入口节点（如「准备文件列表」或直接就是该 function 节点）→ 该 function 节点 → END；或 该 function 节点内再调 create_rag_agent 子图（此时子图 ainvoke 时同样需要传入 callbacks/trace_id 才能上 Langfuse）。

**优点**：脚本退化为「只调一次 flow」，所有逻辑在 flow 内，若希望「整批任务一条 trace、其下多文件为多个 span」可在 function 节点内统一建 trace。  
**缺点**：改动大、需新增/注册 function、flow 结构变化、并行策略（如 asyncio.Semaphore）要迁到 function 内或由 flow 多节点表达，复杂度高。

**结论**：仅在确有「整批一条 trace + 与现有 rag_source_agent 统一用 function 节点编排」需求时再考虑；当前对接 Langfuse 不必依赖方案二。

## 3. 推荐实施步骤（方案一）

### 3.1 改动范围

- **脚本**：`scripts/create_rag_data/run_create_rag_data.py`  
  - 无需改主流程结构；仍为「获取文件列表 → 并行 process_one_file → 汇总」。
- **core**：`scripts/create_rag_data/core/flow_runner.py`  
  - 在 `run_flow` 中：为每次调用生成 `trace_id`；构造 `langfuse_handler = create_langfuse_handler(context={"trace_id": trace_id})`；`config["callbacks"] = [langfuse_handler]`（若 handler 非 None）；在 `RuntimeContext(token_id=..., session_id=..., trace_id=...)` 下执行 `graph.ainvoke(initial_state, config)`。  
  - 可选：将 `trace_id` 写入 `initial_state["trace_id"]`，与 embedding_import 的 state 一致。
- **依赖**：  
  - `backend.infrastructure.observability.langfuse_handler.create_langfuse_handler`  
  - `backend.domain.tools.context.RuntimeContext`  
  - `secrets.token_hex(16)` 或项目内已有的 trace_id 生成方式（与 embedding_import 保持一致）。

### 3.2 与 embedding_import 的对应关系

| embedding_import（runner.py） | create_rag_data（flow_runner.py） |
|------------------------------|------------------------------------|
| `trace_id = secrets.token_hex(16)` | 同上，每文件一次 |
| `session_id = SESSION_ID_PREFIX + record_id` | 已有 `session_id = SESSION_ID_PREFIX + file_id`，可沿用 |
| `build_initial_state_from_record(...)` 内含 trace_id | `build_initial_state(..., trace_id=...)` 在 state 中写入 trace_id |
| `langfuse_handler = create_langfuse_handler(context={"trace_id": trace_id})` | 同上 |
| `config["callbacks"] = [langfuse_handler]` | 同上 |
| `with RuntimeContext(...): await graph.ainvoke(...)` | 同上 |

### 3.3 可选增强：整批一条父 trace

若希望在 Langfuse 上看到「本次脚本运行」为一条父 trace、其下每个文件为子 span，可在 `run_create_rag_data.py` 的 `main()` 中：

- 在进入并行前调用 `set_langfuse_trace_context` 或使用 Langfuse 客户端创建一条父 trace，并得到 `parent_trace_id`；
- 将 `parent_trace_id` 以 metadata 或 context 形式传给各 `process_one_file`，在 `create_langfuse_handler` 或 trace 创建时关联为父级（具体以项目 Langfuse  API 为准）。

此为可选，不影响「每个文件一条 trace」的基线方案一。

## 4. 方案二（function 节点）若要实施的要点

若后续采纳「流程内 function 节点封装」：

- **function 注册**：在项目 function 注册表中新增一项，如 `create_rag_data_batch`，对应实现类/函数从 state 或 config 取「场景记录目录」与「白名单或全部」、拉取文件列表，再循环或并行：读文件 → 调 create_rag_agent 子图（或直接调 LLM）→ 解析 → 落库；并在该 function 内创建/更新 Langfuse trace（例如每个文件一个 observation 或 span）。
- **flow 变更**：例如新增/改造为「单节点 flow：entry → create_rag_data_batch_node → END」，或「builder_node（组文件列表）→ create_rag_data_batch_node → END」；脚本仅 `FlowManager.get_flow(...).ainvoke(initial_state, config)` 一次，并在 ainvoke 时同样传入 `callbacks`/trace 上下文，以便 function 内调用的子图或 LLM 能上报到 Langfuse。
- **与 rag_source_agent 的 format_data_node 区别**：format_data_node 是「单条数据加工」，不负责批量与多次 LLM；create_rag_data 的 function 节点是「批量 + 多次 LLM + 落库」，职责更重，需在实现内显式处理并发与 Langfuse 层级关系。

## 5. 小结

- **推荐**：采用**方案一（脚本侧直接对接 Langfuse）**，在 `flow_runner.run_flow` 中为每次 ainvoke 增加 trace_id、create_langfuse_handler、config["callbacks"]、RuntimeContext，与 embedding_import 的 runner 对齐；**无需**将脚本逻辑封装成 flow 的 function 节点即可完成 Langfuse 对接。
- **可选**：若需「整批一条父 trace」，再在 main() 层增加父 trace 创建与关联。
- **方案二**：仅在确有「统一用 function 节点编排整批任务」需求时再考虑；当前需求下不必依赖「封装成 func 节点」即可接入 Langfuse。
