# pipeline_embedding_record 版本与溯源技术设计

## 1. 目标与背景

- **目标**：在 `pipeline_embedding_records` 表上实现「版本控制」与「运行溯源」，解决多次 task 运行导致重复 embedding 无法区分来源与版本的问题。
- **背景**：参见 `cursor_docs/030205-pipeline_embedding_record多跑溯源扩展设计.md`。本设计在方案选型基础上，明确「版本用独立字段、溯源用 metadata 冗余」的落地方案。

## 2. 设计原则

| 维度 | 方案 | 实现方式 |
|------|------|----------|
| **版本控制** | 方案 B（版本/快照） | 新增独立列：`data_version`、`snapshot_id`、`business_key`，参与版本逻辑与检索。 |
| **运行溯源** | 方案 A（运行/作业 ID） | **不新增列**，将 `batch_job_id`、`batch_task_id` 冗余写入现有 `metadata` 字段，仅用于溯源与排查，不参与版本计算。 |

## 3. 表结构变更

### 3.1 新增列（版本控制）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| data_version | Integer | 可空，默认 1 | 同一 business_key 下的数据版本号，每次重跑/更新可递增 |
| snapshot_id | String(50) | 可空，索引 | 某次「全量快照」或「发布批次」的 ID，可与 batch_job_id 等价或单独生成，用于按快照检索 |
| business_key | String(256) | 可空，索引 | 业务唯一键（如 source_table_name + source_table_id），用于识别「同一条逻辑数据」 |

- **索引建议**：`snapshot_id`、`business_key` 单列索引；若按「某快照下某业务键」查询多，可增加组合索引 `(snapshot_id, business_key)`（按实际查询再定）。
- **兼容**：历史数据三列可为 NULL；新写入由 Step03 批次任务或导入逻辑按规则填充。

### 3.2 表字段变更汇总（实施对照）

| 变更类型 | 字段/位置 | 说明 |
|----------|-----------|------|
| 新增列 | data_version | Integer，nullable=True，default=1；需在 Model 中 `from sqlalchemy import Integer` 并增加 Column |
| 新增列 | snapshot_id | String(50)，nullable=True，index=True |
| 新增列 | business_key | String(256)，nullable=True，index=True |
| 不新增列 | — | batch_job_id、batch_task_id 仅写入 metadata，见 3.3 |
| 迁移 | Alembic | 仅新增上述三列；表名 `pipeline_embedding_records` |

### 3.3 不新增列：溯源信息写入 metadata

- **约定**：将方案 A 的 `batch_job_id`、`batch_task_id` 以固定 key 冗余存入现有 **metadata（JSON）** 字段。
- **metadata 内 key 约定**：

| metadata 内 key | 类型 | 说明 |
|-----------------|------|------|
| batch_job_id | string | 关联 batch_job.id，标识产生该条记录的批次运行 |
| batch_task_id | string | 关联 batch_task.id，标识具体子任务（可选） |

- **写入时机**：由 Step03 的 batch 任务在写入 embedding 时，在原有 metadata 基础上合并写入 `batch_job_id`、`batch_task_id`（若存在）。
- **用途**：仅用于溯源、排查、统计「某次 job/task 产生了哪些记录」；不做唯一约束、不参与版本比较。按 job 查询时可通过 JSON 条件过滤（如 `metadata->>'batch_job_id' = ?`）或应用层过滤。

### 3.4 与现有字段关系

- **现有 metadata**：可能已存其他业务 key，本次仅约定新增 `batch_job_id`、`batch_task_id` 两个 key，与现有用法兼容。
- **is_published / type_ / sub_type**：不变；发布与分类逻辑可继续使用，并可结合 `snapshot_id` 实现「按某快照发布」等策略。

## 4. 版本语义与使用约定

### 4.1 business_key

- **含义**：同一「逻辑数据」的唯一标识，用于判断多条 embedding 是否属于同一条业务数据。
- **建议生成规则**：`{source_table_name}:{source_table_id}` 或项目约定的拼接规则（与 batch_task 的 source_table_name、source_table_id 对齐）。
- **唯一性**：同一 `business_key` 下可存在多条记录（不同 data_version 或 snapshot_id），用于多版本并存。

### 4.2 data_version

- **含义**：同一 business_key 下的版本号，递增表示「同一条逻辑数据的第几版」。
- **使用**：重跑或更新时，可对新写入记录赋 `data_version = 当前最大 version + 1`；查询「当前最新」可按 business_key 取最大 data_version。

### 4.3 snapshot_id

- **含义**：某次全量快照或发布批次的 ID，可与 batch_job_id 一致（一次 job 一次快照），也可单独生成。
- **使用**：按「某次 run」或「某次发布」查询时，用 snapshot_id 过滤；便于多版本并存下按快照检索或回滚。

### 4.4 与 metadata 中 batch_job_id / batch_task_id 的关系

- **版本逻辑**：仅依赖 `data_version`、`snapshot_id`、`business_key`；不依赖 metadata 内的 batch_job_id/batch_task_id。
- **溯源**：需要「某次 job 写了哪些记录」时，查 metadata 中的 batch_job_id（或 batch_task_id）；不参与版本比较与唯一约束。

## 5. Model 与 Repository 变更要点

### 5.1 Model（pipeline_embedding_record.py）

- 在 `PipelineEmbeddingRecordBusinessMixin` 中新增三列：
  - `data_version`：Integer，nullable=True，default=1，comment 见上。
  - `snapshot_id`：String(50)，nullable=True，index=True，comment 见上。
  - `business_key`：String(256)，nullable=True，index=True，comment 见上。
- **不**新增 `batch_job_id`、`batch_task_id` 列；在文档与代码注释中约定写入 metadata 的 key 名（如常量 `METADATA_KEY_BATCH_JOB_ID`、`METADATA_KEY_BATCH_TASK_ID`），便于统一读写。

### 5.2 Repository

- **create/update**：支持传入 `data_version`、`snapshot_id`、`business_key`；若调用方传入 batch_job_id / batch_task_id，应在写入时合并进 `metadata`（不覆盖 metadata 其他 key）。
- **查询**：提供按 `snapshot_id`、`business_key`、`data_version` 的过滤（如按 snapshot 查列表、按 business_key 取最新版本）；按 job 溯源时可通过 metadata 的 JSON 条件或应用层过滤。

### 5.3 metadata 读写约定（建议）

- 写入：若传入 `batch_job_id` / `batch_task_id`，先取当前 `metadata` 字典（或 None），深拷贝后写入 `metadata["batch_job_id"]`、`metadata["batch_task_id"]`，再整体写回。
- 读取：从 `record.metadata_` 中取 `batch_job_id`、`batch_task_id` 用于展示或按 job 过滤；不参与版本判断。

---

## 6. PipelineEmbeddingExecutor 具体实现设计

实现位置：`backend/domain/batch/impl/pipeline_embedding_impl.py`，类 `PipelineEmbeddingExecutor`，方法 `execute_task_impl`。

### 6.1 数据来源（从 task 与改写记录获取）

| 用途 | 来源 |
|------|------|
| job_id / task_id | `task_record.job_id`、`task_record.id`（用于 metadata 溯源） |
| 改写记录 id、embedding_type | `task_record.runtime_params["pipeline_data_items_rewritten_id"]`、`task_record.runtime_params["embedding_type"]` |
| source_table_name / source_table_id | `task_record.source_table_name`、`task_record.source_table_id`（与 CreateHandler 中 TaskPreCreateItem 一致，均为 `pipeline_data_items_rewritten` 与改写记录 id） |

### 6.2 business_key 生成规则

- **约定**：同一「逻辑数据」在本场景下为「同一改写记录 + 同一 embedding 类型」；一条改写记录会生成两条 embedding（Q 与 QA），需在 business_key 中区分。
- **公式**：`business_key = f"{source_table_name}:{source_table_id}:{embedding_type}"`
- **示例**：`pipeline_data_items_rewritten:01ARZ3NDEKTSV4RRFFQ69G5FAV:Q`
- **实现**：在 `execute_task_impl` 内用 `task_record.source_table_name`、`task_record.source_table_id`、当前 `embedding_type` 拼出；若 `source_table_name` 为空则用 `"pipeline_data_items_rewritten"` 与 `rewritten_id` 兜底。

### 6.3 snapshot_id

- **取值**：`snapshot_id = task_record.job_id`（一次 batch job 一次快照，与溯源用 job_id 一致）。

### 6.4 data_version 计算

- **逻辑**：同一 `business_key`（同 snapshot 下可选）下已有记录的最大 `data_version` + 1；若不存在则为 1。
- **实现**：在写入前调用 Repository 新方法 `get_max_data_version_by_business_key(snapshot_id, business_key)` 得到当前最大版本号，`new_data_version = (max_version or 0) + 1`。
- **说明**：同一 job 内同一 business_key 通常只写一次（一个 task 对应一条 Q 或 QA），重试时若需幂等可由上层保证；此处按「每次写入都递增」设计，便于多 run 并存。

### 6.5 metadata 构造（溯源冗余）

- **步骤**：以 `base = {}` 为起点（不依赖改写表是否有 metadata 字段）；写入 `base[METADATA_KEY_BATCH_JOB_ID] = task_record.job_id`、`base[METADATA_KEY_BATCH_TASK_ID] = task_record.id`，将 `base` 作为 `metadata_` 传入 `create`。若后续需把改写记录上其他信息带入 embedding 的 metadata，可在 base 上继续合并。
- **常量**：建议在 Model 或 Repository 模块定义 `METADATA_KEY_BATCH_JOB_ID = "batch_job_id"`、`METADATA_KEY_BATCH_TASK_ID = "batch_task_id"`，Executor 与查询处统一使用，便于维护。

### 6.6 Repository 变更（与 Executor 配合）

- **create 方法**：增加入参 `data_version`、`snapshot_id`、`business_key`（均为 Optional），在调用 `super().create(...)` 时传入；不新增 `batch_job_id`/`batch_task_id` 参数，由调用方合并进 `metadata_` 传入。
- **新增方法**：`get_max_data_version_by_business_key(self, snapshot_id: Optional[str], business_key: str) -> Optional[int]`  
  - 条件：`business_key` 必填；`snapshot_id` 可空，若传则加上 `snapshot_id == snapshot_id` 条件。  
  - 返回：该条件下所有未删记录中 `data_version` 的最大值；若无记录则返回 `None`。  
  - SQL 思路：`select(func.max(PipelineEmbeddingRecordRecord.data_version)).where(...).where(_not_deleted_criterion())`。

### 6.7 execute_task_impl 内写入流程（伪代码）

```
1. 从 task_record 取 job_id, id(task_id), runtime_params, source_table_name, source_table_id
2. 取 rewritten_id, embedding_type；查改写记录 rewritten
3. 拼 embedding_str，调 embedding 得到 embedding_value
4. business_key = f"{source_table_name or 'pipeline_data_items_rewritten'}:{source_table_id or rewritten_id}:{embedding_type}"
5. snapshot_id = job_id
6. max_ver = await embed_repo.get_max_data_version_by_business_key(snapshot_id, business_key)
7. data_version = (max_ver or 0) + 1
8. base_meta = {METADATA_KEY_BATCH_JOB_ID: job_id, METADATA_KEY_BATCH_TASK_ID: task_record.id}
11. record = await embed_repo.create(
       embedding_str=...,
       embedding_value=...,
       embedding_type=...,
       is_published=False,
       type_=...,
       sub_type=...,
       data_version=data_version,
       snapshot_id=snapshot_id,
       business_key=business_key,
       metadata_=base_meta,  # 仅溯源 key，见 6.5
    )
12. commit；return BatchTaskExecutionResult(execution_return_key=record.id)
```

### 6.8 Model 变更（字段定义补充）

在 `PipelineEmbeddingRecordBusinessMixin` 中新增三列，需在文件顶部增加 `Integer` 的导入（若尚未引入）：

```python
from sqlalchemy import Column, Integer, String, Text, Boolean

# 在 embedding_str 之前或按业务顺序插入：
data_version = Column(Integer, nullable=True, default=1, comment="同一 business_key 下数据版本号")
snapshot_id = Column(String(50), nullable=True, index=True, comment="某次全量快照/发布批次 ID")
business_key = Column(String(256), nullable=True, index=True, comment="业务唯一键，识别同一条逻辑数据")
```

metadata 的 key 常量可放在同模块或 `pipeline_embedding_record_repository` 中：

```python
# 溯源信息在 metadata 中的 key，不参与版本逻辑
METADATA_KEY_BATCH_JOB_ID = "batch_job_id"
METADATA_KEY_BATCH_TASK_ID = "batch_task_id"
```

---

## 7. 迁移与兼容

- **数据库**：Alembic 迁移仅新增三列 `data_version`、`snapshot_id`、`business_key`；不修改 metadata 列定义。
- **历史数据**：三列可为 NULL；历史记录的 metadata 中可能无 batch_job_id/batch_task_id，读取时做空值兼容。
- **新数据**：Step03 批次任务写入时，按本设计填充三列，并在 metadata 中冗余 batch_job_id、batch_task_id。

## 8. 文档与引用

- **选型参考**：`cursor_docs/030205-pipeline_embedding_record多跑溯源扩展设计.md`
- **表与 Model 原设计**：`cursor_docs/022801-pipeline_embedding_records表与model-repository技术设计.md`
- **涉及代码**：`backend/infrastructure/database/models/pipeline/pipeline_embedding_record.py`、`backend/infrastructure/database/repository/pipeline/pipeline_embedding_record_repository.py`、`backend/domain/batch/impl/pipeline_embedding_impl.py`（PipelineEmbeddingExecutor.execute_task_impl）。

---

## 9. 小结

| 项目 | 实现 |
|------|------|
| 表/Model 字段 | 新增三列：`data_version`、`snapshot_id`、`business_key`；溯源信息存 metadata |
| 版本控制 | 三列参与版本逻辑；data_version 按 business_key（及 snapshot_id）递增 |
| 运行溯源 | `batch_job_id`、`batch_task_id` 冗余存入现有 `metadata`，不参与版本 |
| 实现位置 | Model/Repository：见 5、6.6、6.8；执行逻辑：`pipeline_embedding_impl.py` 中 `PipelineEmbeddingExecutor.execute_task_impl`（6.1～6.7） |
