# pipeline_embedding_record 多跑溯源扩展设计

## 1. 背景与问题

- **现状**：`pipeline_embedding_records` 表仅包含 embedding 业务字段（embedding_str、embedding_value、embedding_type、is_published、type_、sub_type、metadata_），无与「哪一次任务运行」的关联。
- **问题**：同一批数据被多次执行 Step03（task 任务）时，会重复写入 embedding，无法区分数据来源、无法按「某次运行」查询/回滚/下线，也难以做增量更新与去重。
- **目标**：扩展表设计，使每条 embedding 记录可追溯到「某一次任务运行」或等价的数据来源标识，便于多跑场景下的溯源、去重与发布策略。

本文给出多种工业界常见做法，并给出对应字段扩展方案，供选型。

---

## 2. 工业界方案概览


| 方案                   | 核心思路                   | 典型工业界例子                                        | 适用场景           |
| -------------------- | ---------------------- | ---------------------------------------------- | -------------- |
| A. 运行/作业 ID 溯源       | 每条记录绑定一次「运行」ID         | Airflow DAG Run、Databricks Job Run、dbt run_id  | 按某次执行查询、回滚、重跑  |
| B. 版本/快照             | 同一逻辑数据多版本并存，按版本查       | Delta Lake table version、Snowflake time travel | 多版本并存、按版本检索或回滚 |
| C. 来源通道/租户           | 用来源或租户维度区分数据           | 多租户 SaaS、多数据源同步（source_id/channel）             | 多源入湖、多租户隔离     |
| D. 会话/请求 ID          | 每次请求或任务执行一个 trace 级 ID | LLM 调用 trace_id、Web request_id、分布式追踪           | 全链路追踪、调试       |
| E. 有效时间窗口（SCD Type2） | 同一业务键多段有效时间，按时间取当前有效   | 数仓 SCD Type2、审计表 valid_from/valid_to           | 历史可查、当前生效唯一    |


---

## 3. 方案 A：运行/作业 ID 溯源（推荐优先）

### 工业界例子

- **Airflow**：每次 DAG 执行生成一个 `dag_run_id`，下游任务与日志均挂在该 run 下，可按「某次 DAG 跑」查询或重跑。
- **Databricks**：Job Run 有 `run_id`，Notebook/Job 输出与元数据与 run 绑定。
- **dbt**：每次 `dbt run` 有 `run_id`，incremental 与 run 关联，便于按 run 回滚或重跑。

### 核心思想

每条 embedding 记录绑定「某一次批次运行」：`batch_job_id`（必选）+ 可选 `batch_task_id`。  

- 写入时：由 Step03 的 batch 任务在写 embedding 时写入当前 `job_id` 与（若需要）`task_id`。  
- 查询时：可按「某次 job」筛出该次运行产生的全部 embedding；下线/回滚时可按 job 维度批量软删或标记。

### 表扩展字段建议


| 字段名           | 类型         | 约束    | 说明                                    |
| ------------- | ---------- | ----- | ------------------------------------- |
| batch_job_id  | String(50) | 可空，索引 | 关联 batch_job.id，标识产生该条记录的批次运行         |
| batch_task_id | String(50) | 可空，索引 | 关联 batch_task.id，标识具体子任务（可选，便于更细粒度溯源） |


- **索引**：`(batch_job_id)` 必选；若按 task 查询多则加 `(batch_task_id)`。  
- **兼容**：历史数据可为 NULL，表示「非批次任务写入」；新写入由任务统一填。

### 优点

- 与现有 `batch_job` / `batch_task` 模型一致，无需新概念。  
- 实现简单，查询与下线逻辑清晰（按 job 过滤即可）。

### 缺点

- 仅表达「来自哪次运行」，不直接表达「版本」或「当前是否生效」；若需「仅当前生效」需结合发布或有效时间（见 E）。

---

## 4. 方案 B：版本/快照（Version / Snapshot）

### 工业界例子

- **Delta Lake**：表有 table version，每次写形成一个 version，可按 version 读或回滚。  
- **Snowflake**：Time Travel 按 timestamp 或 query_id 读某一时刻的数据。  
- **内容/推荐**：同一批内容有多版 embedding（如模型升级），用 `embedding_version` 或 `snapshot_id` 区分。

### 核心思想

为「同一条逻辑数据」的多次 embedding 赋予版本或快照 ID，多版本并存，按版本查询或指定「当前使用版本」。

### 表扩展字段建议


| 字段名          | 类型          | 约束      | 说明                                                         |
| ------------ | ----------- | ------- | ---------------------------------------------------------- |
| data_version | Integer     | 可空，默认 1 | 同一业务键下的数据版本号，每次重跑递增                                        |
| snapshot_id  | String(50)  | 可空，索引   | 某次「全量快照」或「发布批次」的 ID，可与 batch_job_id 等价或单独生成                |
| business_key | String(256) | 可空，索引   | 业务唯一键（如 source_table_name + source_table_id），用于识别「同一条逻辑数据」 |


- 同一 `business_key` 下可有多条记录（不同 `data_version` 或 `snapshot_id`），检索时可按 `snapshot_id` 或「最大 data_version」过滤。

### 优点

- 多版本并存，便于 A/B、回滚、审计。

### 缺点

- 需要定义并维护 business_key、版本号或 snapshot 的生成规则；与现有 batch 需打通（如 snapshot_id = job_id）。

---

## 5. 方案 C：来源通道/租户（Source / Channel）

### 工业界例子

- **多租户 SaaS**：按 `tenant_id` 隔离数据；同一表内不同租户数据互不干扰。  
- **多数据源同步**：按 `source_id`、`channel`（如 kafka topic、API 名称）区分数据来源。  
- **数据湖**：不同 pipeline 或团队写入同一湖，用 `source_system`、`pipeline_name` 区分。

### 核心思想

用「来源」维度区分数据：例如 `source_type`（如 "batch_job" / "manual" / "api"）+ `source_id`（如 batch_job_id），或统一一个 `channel` 字符串（如 "step03_batch_20250302"）。

### 表扩展字段建议


| 字段名         | 类型          | 约束    | 说明                                     |
| ----------- | ----------- | ----- | -------------------------------------- |
| source_type | String(32)  | 可空，索引 | 来源类型：batch_job / manual / api / sync 等 |
| source_id   | String(128) | 可空，索引 | 来源 ID（如 batch_job_id、导入任务 id）          |
| channel     | String(64)  | 可空，索引 | 通道/批次名（可选，便于按「某次导入」或「某次跑批」命名查询）        |


- 多跑场景：同一批数据多次跑时，可用不同 `channel` 或同一 `source_type`+ 不同 `source_id`（即 job_id）区分。

### 优点

- 扩展性好，后续有 API 导入、手工导入等都可复用 source_type/source_id。

### 缺点

- 与「运行」概念略间接，若仅做「按某次 batch 跑」溯源，方案 A 更直观。

---

## 6. 方案 D：会话/请求 ID（Session / Request / Trace ID）

### 工业界例子

- **LLM 与可观测**：每次调用带 `trace_id`、`span_id`，便于在 Langfuse 等平台按请求追踪。  
- **Web**：每个请求一个 `request_id`，日志与下游写入统一挂在该 request 下。  
- **分布式追踪**：OpenTelemetry、Jaeger 的 trace_id。

### 核心思想

每次「任务执行」或「写 embedding 的请求」生成一个唯一 ID（如 `run_session_id`、`trace_id`），每条 embedding 记录带该 ID，便于全链路追踪与按会话排查。

### 表扩展字段建议


| 字段名            | 类型         | 约束    | 说明                                                      |
| -------------- | ---------- | ----- | ------------------------------------------------------- |
| run_session_id | String(64) | 可空，索引 | 单次「写 embedding」的会话/请求 ID（可与 batch_job_id 或单独生成 ULID 一致） |
| trace_id       | String(64) | 可空    | 可观测 trace_id（可选，便于与 Langfuse 等关联）                       |


- 若 `run_session_id` 与 `batch_job_id` 一一对应，则与方案 A 等价；若每次「写一条」都生成新 session，则更细粒度、适合调试。

### 优点

- 与可观测、日志体系自然融合。

### 缺点

- 仅做「多跑溯源」时，通常不需要「每条一个 session」；与 job 对齐即可，否则存储与索引成本略高。

---

## 7. 方案 E：有效时间窗口（SCD Type2 风格）

### 工业界例子

- **数仓 SCD Type2**：同一业务键多行，每行有 `valid_from`、`valid_to`，查询「当前」取 `valid_to IS NULL` 或最大 valid_from。  
- **审计/合规**：记录何时生效、何时被替代，便于历史查询与合规。

### 核心思想

同一业务键（如 source 表 + 主键）可对应多条 embedding 记录，通过 `valid_from` / `valid_to` 表示生效区间；新一次 run 写入新记录并关闭旧记录的 `valid_to`，使「当前有效」唯一。

### 表扩展字段建议


| 字段名          | 类型           | 约束    | 说明                           |
| ------------ | ------------ | ----- | ---------------------------- |
| business_key | String(256)  | 可空，索引 | 业务唯一键                        |
| valid_from   | DateTime(TZ) | 可空    | 生效开始时间                       |
| valid_to     | DateTime(TZ) | 可空    | 生效结束时间，NULL 表示当前有效           |
| batch_job_id | String(50)   | 可空，索引 | 产生该条记录的 job（可选，便于按 job 批量操作） |


- 查询「当前有效」：`valid_to IS NULL`（或按时间点查 `valid_from <= t < valid_to`）。

### 优点

- 历史可查、当前生效唯一，适合强审计与「仅用最新一次 run」的检索。

### 缺点

- 写入逻辑复杂（需更新旧行的 valid_to）；需要明确 business_key 的定义与唯一性。

---

## 8. 组合建议与选型

- **仅解决「多跑溯源、按某次运行查询/下线」**：优先采用 **方案 A（batch_job_id + 可选 batch_task_id）**，实现成本低、与现有 batch 模型一致。  
- **若未来要支持多版本并存、按版本检索**：在 A 基础上增加 **方案 B** 的 `data_version` / `snapshot_id`（可与 job_id 对齐）。  
- **若有多数据源/多通道写入**：在 A 上增加 **方案 C** 的 `source_type` / `source_id` 或 `channel`。  
- **若需与可观测深度结合**：在 A 上增加 **方案 D** 的 `run_session_id` 或 `trace_id`（可与 job_id 或 task_id 对齐）。  
- **若需「当前唯一有效」与历史审计**：考虑 **方案 E**，并与 A 组合（用 batch_job_id 标识写入来源）。

**最小可行扩展（推荐第一步）**：  
在 `pipeline_embedding_record` 上仅增加：

- `batch_job_id`（String(50), 可空, 索引）
- （可选）`batch_task_id`（String(50), 可空, 索引）

写入时由 Step03 的 batch 任务将当前 `job_id` / `task_id` 写入；历史数据保持为 NULL。这样即可区分多次 task 运行产生的 embedding 数据来源，并为后续按 job 下线、重跑、统计打好基础。

---

## 9. 与现有模型的关系

- **batch_job**：一次 Step03 批次执行；`pipeline_embedding_records.batch_job_id` → `batch_job.id`。  
- **batch_task**：该批次下的单条子任务；`pipeline_embedding_records.batch_task_id` → `batch_task.id`。  
- 现有字段 **is_published** / **type_** / **sub_type** / **metadata_** 不变；发布策略可在此基础上实现（例如：仅将某次 job 产生的记录标记为 is_published，或仅某 job 参与检索）。

---

## 10. 文档与变更说明

- **设计文档**：本文档 `cursor_docs/030205-pipeline_embedding_record多跑溯源扩展设计.md`。  
- **涉及模型**：`backend/infrastructure/database/models/pipeline/pipeline_embedding_record.py`。  
- **后续步骤**：选定方案后，在 Model 的 `PipelineEmbeddingRecordBusinessMixin` 中增加对应字段，并做 Alembic 迁移；Repository/API 按需增加按 `batch_job_id`（及 task_id）的查询与过滤。

