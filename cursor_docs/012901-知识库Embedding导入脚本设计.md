# 知识库 Embedding 导入脚本技术设计文档

## 1. 目标与范围

### 1.1 目标

实现独立脚本，从 **知识库表**（`KnowledgeBaseRecord`，见 `backend/infrastructure/database/models/knowledge_base.py`）读取原始数据，运行 **embedding_knowledge_agent** 流程（`config/flows/embedding_knowledge_agent/flow.yaml`），使流程能正常执行并将结果写入 **embedding_records** 表（及向量库）。

### 1.2 范围

- **数据源**：`KnowledgeBaseRecord` 表（表名由 `TABLE_PREFIX` + `knowledge_base` 组成，如 `gd2502_knowledge_base`）。
- **流程**：`config/flows/embedding_knowledge_agent/flow.yaml`（与现有 `embedding_agent` 同构：format_data_node → embedding_node → insert_data_to_vector_db_node）。
- **脚本位置与风格**：脚本存放在 `scripts/embedding_import_qa` 下，代码风格参考 `scripts/embedding_import`，**不直接引用** `scripts/embedding_import` 的代码，仅借鉴其思路（加载流程、排除已处理、并行执行、state 构建等）。

### 1.3 与现有 embedding_import 的差异

| 项目         | embedding_import                    | embedding_import_qa（本设计）           |
|--------------|-------------------------------------|----------------------------------------|
| 数据源表     | blood_pressure_session_records      | knowledge_base（gd2502_knowledge_base）|
| 流程         | embedding_agent                    | embedding_knowledge_agent              |
| 排除已处理   | 按 EmbeddingRecord.source_* 排除 BP | 按 EmbeddingRecord.source_* 排除 KB   |
| 初始 state   | 从 BloodPressureSessionRecord 组装  | 从 KnowledgeBaseRecord 组装            |

**说明**：本设计采用 §6 改进方案后，**before_embedding_func 不再兼容**原 `scripts/embedding_import` 的调用方式（即不再查 BloodPressureSessionRecord 取 message_id、ai_response）。若仍需用 embedding_import 跑血压表数据，需在 embedding_import 的 state_builder 中**显式写入 edges_var.ai_response**（如从 BloodPressureSessionRecord.new_session_response 取）及 source_id、source_table_name，并确保流程使用版本号按 source_id+source_table_name 计算的新实现；否则须改用 embedding_knowledge_agent 流程或其它入口。

---

## 2. 整体流程

1. **加载流程**：先加载模型供应商配置，再加载 `embedding_knowledge_agent` 流程图。
2. **查询原始数据**：从知识库表查询未处理记录（排除已在 embedding_records 中存在的记录）。
3. **加工并运行流程**：将每条知识库记录加工成流程首节点所需 state，并行执行流程（format_data_node → embedding_node → insert_data_to_vector_db_node），结果入库。

---

## 3. 详细设计

### 3.1 加载流程（参考 run_embedding_import_parallel.py:138-155）

- **顺序**：必须先加载模型供应商配置，再加载流程图（否则流程内依赖的 LLM/Embedding 等可能不可用）。
- **步骤**：
  1. 使用 `find_project_root()` 得到项目根目录，加载 `config/model_providers.yaml`，调用 `ProviderManager.load_providers(config_path)`。
  2. 使用 `FlowManager.get_flow(FLOW_KEY)` 获取编译后的图；`FLOW_KEY` 需与要运行的流程对应。
- **流程 Key 说明**：`FlowManager` 的 key 来自各流程目录下 `flow.yaml` 的 **name** 字段。当前 `config/flows/embedding_knowledge_agent/flow.yaml` 的 name 为 `embedding_agent`，若与其它流程重名会互相覆盖。建议将该流程的 **name 改为 `embedding_knowledge_agent`**，脚本中设置 `FLOW_KEY = "embedding_knowledge_agent"`，以便与血压场景的 `embedding_agent` 区分。

### 3.2 查询原始数据并排除已处理（参考 run_embedding_import_parallel.py:159-160）

- **表**：`KnowledgeBaseRecord`（ORM 类），对应表名 `KnowledgeBaseRecord.__tablename__`（如 `gd2502_knowledge_base`）。
- **排除逻辑**：与 embedding_import 一致，使用 **LEFT JOIN + IS NULL**：
  - 关联条件：`EmbeddingRecord.source_table_name == <知识库表名>` 且 `EmbeddingRecord.source_record_id == KnowledgeBaseRecord.id`。
  - 过滤：`EmbeddingRecord.id.is_(None)`，即只保留尚未在 embedding_records 中落过一条的记录。
- **排序与分页**：`ORDER BY KnowledgeBaseRecord.created_at`，`LIMIT limit OFFSET offset`，便于稳定分批与重跑。

知识库表名建议在脚本内通过常量或从 `KnowledgeBaseRecord.__tablename__` 获取，保证与 `before_embedding_func` 中写入的 `source_table_name` 一致。

### 3.3 将原始数据加工成流程可用的 state，并运行流程

流程首节点为 **format_data_node**，对应实现为 **before_embedding_func**（`backend/domain/flows/implementations/before_embedding_func.py`）。该节点**仅从 state 读取数据，不再查询任何业务表**（见 §6 及下文）。从 state 中读取的数据如下：

```text
edges_var = state.get("edges_var", {})
  - scene_summary         = edges_var.get("scene_summary", "")
  - optimization_question = edges_var.get("optimization_question", "")
  - input_tags            = edges_var.get("input_tags", [])
  - response_tags         = edges_var.get("response_tags", [])
  - ai_response           = edges_var.get("ai_response", "")   # 用于拼 embedding_str，由调用方在 state 初始化时从业务表填入

prompt_vars = state.get("prompt_vars", {})
  - source_id             = prompt_vars.get("source_id")
  - source_table_name     = prompt_vars.get("source_table_name")
```

- **ai_response** 作为 `_format_embedding_str(scene_summary, optimization_question, ai_response)` 的入参，**取值来源统一为 edges_var**，before_embedding_func 内不再通过 SQL 查询业务表获取。
- 脚本在 **初始化 state** 时，必须为上述字段（含 **edges_var.ai_response**）提供值，且取值逻辑需与数据源一致。下面给出从 **KnowledgeBaseRecord** 到 state 的映射，供 Review 与实现使用。

#### 3.3.1 从 KnowledgeBaseRecord 到 state 的取值逻辑（供 Review）

| state 路径 | 含义 | 取值来源 | 说明 |
|------------|------|----------|------|
| **edges_var.scene_summary** | 场景摘要 | `KnowledgeBaseRecord.scene_summary` | 可为空字符串，before_embedding_func 会做 strip。 |
| **edges_var.optimization_question** | 优化问题 | `KnowledgeBaseRecord.optimization_question` | 同上。 |
| **edges_var.input_tags** | 输入标签 | `KnowledgeBaseRecord.input_tags` | 表字段为 JSONB，直接 list；若为 None 则传 `[]`。 |
| **edges_var.response_tags** | 回复标签 | `KnowledgeBaseRecord.response_tags` | 同上。 |
| **edges_var.ai_response** | 用于拼 embedding_str 的回复/正文 | 从业务表对应字段获取，知识库建议：`KnowledgeBaseRecord.reply_example_or_rule` 或 `raw_material_full_text`（空则回退） | **必填**。脚本在 state 初始化时从业务表取好写入 edges_var；before_embedding_func 仅从 edges_var 读取，不查业务表。 |
| **prompt_vars.source_id** | 数据源记录 ID | `KnowledgeBaseRecord.id` | 用于 before_embedding_func 写 EmbeddingRecord.source_record_id、版本号计算（§6）。 |
| **prompt_vars.source_table_name** | 数据来源表名 | `KnowledgeBaseRecord.__tablename__` | 与排除已处理、EmbeddingRecord 入库、版本号计算（§6）一致，如 `gd2502_knowledge_base`。 |

除上述字段外，流程和 before_embedding_func 还会使用：

- **trace_id**、**session_id**：脚本在 runner 层生成（如 `session_id = f"{SESSION_ID_PREFIX}{record.id}"`，trace_id 32 位十六进制）。
- **token_id**：脚本占位符（如 `TOKEN_ID_PLACEHOLDER`）即可。

**与 before_embedding_func 的约定（§6 落地）**：**before_embedding_func 不再兼容** `scripts/embedding_import` 下的老流程，**直接移除对 BloodPressureSessionRecord 的所有依赖**（不再查询 BP 表取 message_id、ai_response）。版本号按 **source_id + source_table_name** 在 EmbeddingRecord 上计算；**ai_response** 统一从 **edges_var** 读取（即 `edges_var.get("ai_response", "")`），作为 `_format_embedding_str` 的入参。EmbeddingRecord 的 message_id 写入时可用 source_id 或空，由实现决定，不参与版本计算。

### 3.4 并行执行（参考 run_embedding_import_parallel.py:171-172）

- 与 embedding_import 一致：对本次拉取到的多条知识库记录，使用 **asyncio** 并行执行多条流程。
- 使用 **asyncio.Semaphore(max_concurrent)** 限制并发数，避免超过 Embedding/LLM 限流；单条执行封装为“从 record 构建 state → 可选 dry_run → graph.ainvoke”。
- 汇总成功数、失败数，失败时打日志并可选退出码非 0。

### 3.5 初始化 state 的专有上下文（脚本侧，对应 runner 类似 runner.py:48-49）

- 脚本在 **embedding_import_qa** 下应有自己的 **state_builder**（或等价模块），**不引用** `scripts/embedding_import`。
- 在“单条执行”的入口（类似 runner 的 run_one）中，先调用 **build_initial_state_from_record(record, session_id, trace_id)**，其中 **record** 为 **KnowledgeBaseRecord**。
- **build_initial_state_from_record** 内部按 §3.3.1 的表格，从 `KnowledgeBaseRecord` 拼出：
  - **edges_var**：scene_summary、optimization_question、input_tags、response_tags、**ai_response**（从业务表对应字段获取，如 reply_example_or_rule 或 raw_material_full_text）；
  - **prompt_vars**：source_id、source_table_name；
  - 以及 **session_id**、**trace_id**、**token_id**、**current_message** / **flow_msgs** 等流程必需字段（若流程不需要可给占位或空）。
- 这样流程首节点 before_embedding_func 即可**仅从 state 读取**（含 ai_response 从 edges_var 取），不再查询任何业务表。

---

## 4. 脚本目录与模块划分（建议）

在 **scripts/embedding_import_qa** 下建议结构（风格对齐 embedding_import，但不 import 其代码）：

```text
scripts/embedding_import_qa/
  __init__.py           # 暴露 FLOW_KEY、DEFAULT_BATCH_SIZE、SESSION_ID_PREFIX、build_initial_state_from_record 等
  run_embedding_import_qa_parallel.py   # 入口：加载配置与流程、查未处理、并行 run_one、统计与日志
  core/
    __init__.py
    config.py           # FLOW_KEY、DEFAULT_BATCH_SIZE、SESSION_ID_PREFIX、TOKEN_ID_PLACEHOLDER、知识库表名常量
    repository.py       # 使用 KnowledgeBaseRecord + EmbeddingRecord，fetch_records_excluding_processed(limit, offset)
    state_builder.py    # build_initial_state_from_record(kb_record, session_id, trace_id) -> FlowState（含 §3.3.1 映射）
    runner.py           # run_one(record, graph, dry_run)、run_batch_parallel(records, graph, max_concurrent, dry_run)
```

- **config**：流程 key、批量大小、并发数默认值、session_id 前缀、占位 token_id、知识库表名（可从 `KnowledgeBaseRecord.__tablename__` 取）。
- **repository**：同步 Session、`fetch_records_excluding_processed`（LEFT JOIN embedding_records，条件为知识库表名 + source_record_id）。
- **state_builder**：仅依赖 KnowledgeBaseRecord 与 §3.3.1，输出含 edges_var、prompt_vars 的完整 state。
- **runner**：与 embedding_import 的 runner 思想一致：单条 build state + ainvoke；批次用 asyncio.gather + Semaphore。

---

## 5. 与 before_embedding_func 的配合（领域层扩展）

- 脚本只负责“查知识库表 + 拼 state + 调流程”；**识别数据源并写 embedding 表**仍在 **before_embedding_func** 内完成。
- **不再兼容老流程**：before_embedding_func **不再兼容** `scripts/embedding_import` 下的流程，**直接移除对 BloodPressureSessionRecord 的所有依赖**（如原“查询 BP 表取 message_id、ai_response”的代码全部删除），领域层不引用任何业务表。
- **版本号**：按 §6，版本号统一按 **source_id + source_table_name** 在 EmbeddingRecord 上计算，入参仅来自 state，不查源表。
- **ai_response 从 edges_var 取**：before_embedding_func 内“读取 edges_var”的逻辑（对应实现中约 193 行）需**升级**：在读取 scene_summary、optimization_question、input_tags、response_tags 后，**增加** `ai_response = edges_var.get("ai_response", "")`；`_format_embedding_str(scene_summary, optimization_question, ai_response)` 的 ai_response 入参即来自此处，**不再**在代码中通过 SQL 查询业务表获取。
- **message_id**：创建 EmbeddingRecord 时 message_id 可写 source_id 或空，不参与版本计算；由实现决定。
- 这样同一份 flow 仅依赖 state（edges_var + prompt_vars），由**调用方**在 state 初始化时从业务表取好并填入 edges_var.ai_response 等，before_embedding_func 只读 state + 写 EmbeddingRecord，适用于知识库、后续其他数据源等。

---

## 6. before_embedding_func 改进方案（版本号与依赖解耦）

当前 `before_embedding_func` 存在两处与具体业务表耦合的问题：（1）版本号按 **message_id** 在 EmbeddingRecord 上查 max(version)，而 message_id 需从 BloodPressureSessionRecord 查出；（2）**ai_response** 从 BP 表查询获取。本方案**不再兼容** `scripts/embedding_import` 下的老流程，**直接移除对 BloodPressureSessionRecord 的所有依赖**，并做如下改进。

### 6.1 改进目标

- **版本号计算**：改为仅用 state 中已有的 **source_id**、**source_table_name** 在 EmbeddingRecord 上做查重与递增，不查任何业务表。
- **ai_response**：作为 `_format_embedding_str` 的入参，**取值来源统一为 state 的 edges_var**（`edges_var.get("ai_response", "")`），不再在代码中调用 SQL 查询业务表。
- **语义统一**：“同一数据源”在排除已处理、写入 EmbeddingRecord、版本递增三处均使用 **(source_table_name, source_record_id)**，与现有表结构一致，且多数据源通用。

### 6.2 版本号计算逻辑（具体化）

**原逻辑（已废弃）：**

- 使用 `message_id`（来自 BloodPressureSessionRecord）在 EmbeddingRecord 上查询，新版本号 = max_version + 1。

**新逻辑（改进后）：**

- 使用 **source_record_id + source_table_name** 在 EmbeddingRecord 上查询：  
  `SELECT max(version) FROM embedding_records WHERE source_record_id = ? AND source_table_name = ?`
- 新版本号 = max_version + 1（若不存在则为 0）。
- **入参**：仅需 state 中的 `prompt_vars.source_id`、`prompt_vars.source_table_name`，无需再查任何源表。

**实现要点：**

- `_calculate_next_version(session, message_id)` 改为 `_calculate_next_version(session, source_record_id: str, source_table_name: str)`。
- 查询条件改为：`EmbeddingRecord.source_record_id == source_record_id` 且 `EmbeddingRecord.source_table_name == source_table_name`，对结果取 `func.max(EmbeddingRecord.version)`。
- 调用处在 execute 内：在校验完 source_id、source_table_name 之后直接调用，**删除**“查询 BloodPressureSessionRecord 取 message_id、ai_response”的全部代码。

### 6.3 before_embedding_func 读 state 逻辑（具体化）

- **删除**：对 BloodPressureSessionRecord 的 import、`_get_blood_pressure_session_record` 方法、以及 execute 内“查询 BP 表 → 取 message_id、ai_response”的代码（如原 215-223 行）。
- **升级“读取 edges_var”逻辑**（对应实现中约 193 行）：在读取 scene_summary、optimization_question、input_tags、response_tags 之后，**增加**一行：
  - `ai_response = edges_var.get("ai_response", "")`
- **ai_response 入参**：`_format_embedding_str(scene_summary, optimization_question, ai_response)` 的第三个参数即来自上述 edges_var，不再从业务表查询。
- **message_id**：创建 EmbeddingRecord 时 message_id 可写 `source_id` 或空，不参与版本计算；由实现决定。

### 6.4 state 初始化（调用方职责）

- **edges_var** 必须包含 **ai_response**：由**调用方**在 state 初始化时从业务表对应字段取好并写入 `edges_var["ai_response"]`。知识库脚本从 `KnowledgeBaseRecord.reply_example_or_rule` 或 `raw_material_full_text` 等取；其他数据源脚本从各自业务表字段取。
- before_embedding_func 只读 state（edges_var + prompt_vars），不查业务表，领域层不引用 BloodPressureSessionRecord / KnowledgeBaseRecord。

### 6.5 小结（改进方案）

- **不再兼容老流程**：before_embedding_func 不再兼容 `scripts/embedding_import`，直接移除 BloodPressureSessionRecord 的所有依赖。
- **版本号**：按 **(source_record_id, source_table_name)** 在 EmbeddingRecord 上查 max(version) 并 +1，入参仅来自 state。
- **ai_response**：从 **edges_var** 读取（`edges_var.get("ai_response", "")`），作为 `_format_embedding_str` 入参；由调用方在 state 初始化时从业务表填入 edges_var.ai_response。
- **message_id**：仅作 EmbeddingRecord 的存储字段，可写 source_id 或空，不参与版本计算。

实现上述改进后，before_embedding_func 的依赖边界收窄为“state + EmbeddingRecord”，符合领域分层要求。

---

## 7. 小结

- **脚本**：在 `scripts/embedding_import_qa` 下实现“加载流程 → 查未处理知识库记录 → 按条构建 state（§3.3.1，**含 edges_var.ai_response**）→ 并行执行流程”。
- **排除已处理**：LEFT JOIN embedding_records，按知识库表名 + source_record_id 排除。
- **state 构建**：由 §3.3.1 的映射表明确定义；**state 初始化必须包含 edges_var.ai_response**，从业务表对应字段获取（知识库用 reply_example_or_rule 或 raw_material_full_text）；runner 层仅调用 state_builder，不引用 embedding_import。
- **领域层（§6）**：before_embedding_func **不再兼容** `scripts/embedding_import`，**直接移除对 BloodPressureSessionRecord 的所有依赖**；版本号按 **source_id + source_table_name** 计算；**ai_response 从 edges_var 读取**，作为 `_format_embedding_str` 入参，不在代码中查业务表；message_id 写 EmbeddingRecord 时可用 source_id 或空。

按此设计（含 §6 改进）实现后，即可从知识库表拉取未处理数据，运行 embedding_knowledge_agent 流程并完成入库与向量写入，before_embedding_func 依赖边界收窄为“state + EmbeddingRecord”。

---

## 8. 开发进度

| 任务 | 状态 | 说明 |
|------|------|------|
| §6 before_embedding_func 改进 | 已完成 | 移除 BloodPressureSessionRecord 依赖；版本号按 source_record_id+source_table_name 计算；ai_response 从 edges_var 读取；message_id 写 source_id。 |
| scripts/embedding_import_qa | 已完成 | config、repository、state_builder、runner、run_embedding_import_qa_parallel.py 已实现；不引用 embedding_import。 |
| flow.yaml name | 已完成 | config/flows/embedding_knowledge_agent/flow.yaml 的 name 改为 embedding_knowledge_agent。 |
| 测试用例 | 已完成 | cursor_test/test_embedding_import_qa_state_builder.py：state_builder 从 KnowledgeBaseRecord 组装 state（含 edges_var.ai_response、prompt_vars）。cursor_test/test_before_embedding_func_no_bp_dependency.py：before_embedding_func 无 BP 依赖、版本号按 source_record_id+source_table_name、ai_response 从 edges_var 读取。 |
| 设计文档进度章节 | 已完成 | 本节 §8。 |
