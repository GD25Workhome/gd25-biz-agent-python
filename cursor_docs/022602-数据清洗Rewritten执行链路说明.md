# 数据清洗 Rewritten 执行链路说明

本文档梳理「新建批次 → 在批次中运行待清洗数据 → 生成 pipeline_data_items_rewritten 数据」的完整执行链路。对应 API 入口：`POST /data-cleaning/datasets/{dataset_id}/items/rewritten/execute` 及批次运行、队列消费流程。

设计文档参考：
- cursor_docs/021001-Rewritten流程批量异步执行技术设计.md
- cursor_docs/021101-Rewritten批次表与创建流程设计.md
- cursor_docs/021105-Step02批次任务队列与运行停止技术设计.md

---

## 一、整体流程概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. 新建批次                                                                   │
│    POST /data-cleaning/datasets/{dataset_id}/items/rewritten/execute         │
│    → create_rewritten_batch()                                                 │
│    → 写 pipeline_rewritten_batches + pipeline_data_items_rewritten (init)    │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. 在批次中运行                                                               │
│    POST /data-cleaning/rewritten-batches/run { "batch_code": "..." }          │
│    → enqueue_batch() → 待处理任务入队（内存队列）                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. 队列消费者（应用启动时 start_consumers）                                      │
│    取任务 → update_status_to_processing_if_init → run_one_rewritten()         │
│    → Flow(rewritten_data_service_agent) → update_rewritten_data_func           │
│    → 更新 pipeline_data_items_rewritten 为 success/失败写入 failed            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、链路一：新建批次

### 2.1 入口

- **接口**：`POST /data-cleaning/datasets/{dataset_id}/items/rewritten/execute`
- **路由**：`backend/app/api/routes/data_cleaning.py` → `execute_rewritten_endpoint`
- **请求体**：`RewrittenExecuteRequest`，支持两种模式：
  - `item_ids`：按数据项 ID 列表
  - `query_params`：按条件筛选（如 `status`、`unique_key`、`source`、`keyword`），传 `{}` 表示该 dataset 下全部

### 2.2 调用链

1. **参数校验**：至少提供 `item_ids` 或 `query_params`；校验 `dataset_id` 对应数据集合存在。
2. **调用** `create_rewritten_batch(dataset_id, session, item_ids=..., query_params=...)`  
   实现在 `backend/pipeline/rewritten_service.py`。

### 2.3 create_rewritten_batch 内部逻辑

| 步骤 | 说明 | 代码位置 |
|------|------|----------|
| 1 | 根据 `item_ids` 或 `query_params` 查询待清洗数据 | `DataSetsItemsRepository.get_by_ids()` 或 `get_list_by_conditions()`，数据来自 `pipeline_data_sets_items`（或项目内等价表） |
| 2 | 若无记录则直接返回空结果 | `RewrittenBatchCreateResult(batch_code="", total=0)` |
| 3 | 生成批次号 | `batch_code = datetime.now().strftime("%Y%m%d%H%M%S")` |
| 4 | 写批次表 | `RewrittenBatchRepository.create(batch_code, total_count, create_params)` → 表 **pipeline_rewritten_batches** |
| 5 | 批量创建改写任务（init） | `DataItemsRewrittenRepository.create_init_batch(records, batch_code, dataset_id)` → 表 **pipeline_data_items_rewritten**，每条：`source_dataset_id`、`source_item_id`、`status=init`、`batch_code`；已存在同源且状态为 init/processing/success 的会跳过 |

### 2.4 返回与库表

- **返回**：`RewrittenExecuteResponse(success=True, message="批次已创建，任务将异步执行", batch_code=..., total=created)`  
- **库表**：
  - **pipeline_rewritten_batches**：一条批次记录（batch_code、total_count、create_params 等）
  - **pipeline_data_items_rewritten**：本批次对应的多条记录，状态均为 `init`，仅含来源信息，尚未写入改写结果

---

## 三、链路二：在批次中运行（入队）

### 3.1 入口

- **接口**：`POST /data-cleaning/rewritten-batches/run`
- **请求体**：`RewrittenBatchRunRequest { "batch_code": "..." }`
- **路由**：`run_rewritten_batch`（同上路由文件）

### 3.2 调用链

1. 校验 `batch_code` 非空。
2. `RewrittenBatchRepository.get_by_batch_code(batch_code)` 校验批次存在。
3. 调用 `enqueue_batch(batch_code, session)`，实现在 `backend/pipeline/rewritten_queue_service.py`。

### 3.3 enqueue_batch 内部逻辑

| 步骤 | 说明 |
|------|------|
| 1 | `DataItemsRewrittenRepository.get_pending_by_batch_code(batch_code)`：查询该批次下 `status in (init, processing)` 且来源 ID 非空的记录 |
| 2 | 对每条记录：若其 `id` 不在内存集合 `_in_flight_ids` 中，则先 `update_status(rid, STATUS_INIT)`，再放入内存队列 `_queue.put_nowait((record_id, batch_code))`，并把 `record_id` 加入 `_in_flight_ids` |
| 3 | 返回本次入队数量 |

说明：运行「在批次中运行」后，任务不会自动执行，需要依赖已启动的**队列消费者**从 `_queue` 取任务并执行。

---

## 四、链路三：生成 pipeline_data_items_rewritten 数据（消费者执行）

### 4.1 消费者启动

- **位置**：`backend/main.py` 的 lifespan。
- **逻辑**：在应用启动时调用 `rewritten_queue_service.start_consumers()`，启动固定数量（如 4 个）的 `_consumer_loop` 协程，常驻运行直至应用关闭。

### 4.2 单消费者循环 _consumer_loop

| 步骤 | 说明 | 代码位置 |
|------|------|----------|
| 1 | `await _queue.get()` 从内存队列取出一条 `(record_id, batch_code)` | rewritten_queue_service |
| 2 | 用 `DataItemsRewrittenRepository.get_by_id(record_id)` 取完整记录，若无则 `_mark_failed(record_id, "记录不存在")` | 同上 |
| 3 | **占位防重**：`update_status_to_processing_if_init(record_id)`，仅当当前状态为 `init` 时更新为 `processing`；若未更新到行则跳过执行（避免重复消费） | data_items_rewritten_repository |
| 4 | 调用 `run_one_rewritten(rec)` 执行单条改写 | rewritten_service |

### 4.3 run_one_rewritten 与 Flow

- **文件**：`backend/pipeline/rewritten_service.py` 的 `run_one_rewritten(rec: DataItemsRewrittenRecord)`。
- **逻辑概要**：
  - 若 `rec.status` 已是 `success` 或 `failed`，直接返回。
  - 用 `source_dataset_id`、`source_item_id` 查 `DataSetsItemsRecord`（来源数据项）；查不到则把该条改写记录更新为 `failed` 并返回。
  - 获取 Flow：`FlowManager.get_flow("rewritten_data_service_agent")`（与 config 中 flow 名称一致）。
  - 使用 `build_state_from_record(item_record, session_id, trace_id, rewritten_record_id=rec.id)` 构建初始状态，其中 **rewritten_record_id** 传入当前 `pipeline_data_items_rewritten` 的主键，供后续更新节点使用。
  - 调用 `graph.ainvoke(initial_state, config)` 执行流程。

### 4.4 Flow 内节点与写入 pipeline_data_items_rewritten

- **流程名**：`rewritten_data_service_agent`（配置在 config/flows/pipeline_step2/flow.yaml 等）。
- **关键节点**：
  1. **rewritten_agent_node**：基于 state 中的上下文、当前消息等调用 LLM，产出改写结果，写入 state 的 **edges_var**（如场景描述、患者提问、回复案例、回复规则、场景/子场景、改写依据、场景置信度、标签等）。
  2. **update_rewritten_data_node**：对应实现类 `UpdateRewrittenDataNode`（`backend/domain/flows/implementations/update_rewritten_data_func.py`）。

### 4.5 update_rewritten_data_func 写入逻辑

| 步骤 | 说明 |
|------|------|
| 1 | 从 state 取 `edges_var` 和 `rewritten_record_id`（来自创建批次时写入的 pipeline_data_items_rewritten 主键） |
| 2 | 若 `edges_var` 中无有效改写结果，则更新该记录为 `status=failed` 并写入失败原因等 `execution_metadata` |
| 3 | 若有有效改写结果，则根据映射（如「患者提问」→ `rewritten_question`、「回复案例」→ `rewritten_answer` 等）拼装更新字段，并设置 `status=success`、`trace_id` 等 |
| 4 | `DataItemsRewrittenRepository.update(rewritten_record_id, **kwargs)` 写回 **pipeline_data_items_rewritten** 表 |

至此，单条「待清洗数据」对应的 `pipeline_data_items_rewritten` 记录由 `init` → `processing` → **success**（或 **failed**），改写结果落库。

### 4.6 状态与异常

- 执行过程中若抛错，由消费者或 `run_one_rewritten` 侧调用 `_mark_failed(record_id, reason)`，将对应记录更新为 `status=failed` 并写入 `execution_metadata`。
- 消费者在每次处理结束后从 `_in_flight_ids` 移除该 `record_id`，便于后续同一任务可再次入队（如单条「再次运行」接口）。

---

## 五、相关表与 API 小结

| 表名 | 作用 |
|------|------|
| pipeline_rewritten_batches | 批次元数据：batch_code、total_count、create_params 等 |
| pipeline_data_items_rewritten | 每条待/已改写数据：来源 source_*、batch_code、status（init/processing/success/failed）、改写结果字段（scenario_description、rewritten_question、rewritten_answer 等） |

| 接口 | 作用 |
|------|------|
| POST .../datasets/{id}/items/rewritten/execute | 新建批次并生成 init 记录（不执行） |
| POST .../rewritten-batches/run | 按 batch_code 将待处理任务入队 |
| GET .../rewritten-batches | 批次列表及统计 |
| GET .../rewritten-batches/queue-stats | 队列排队数、执行中+排队总数 |
| GET .../data-items-rewritten | 查询 pipeline_data_items_rewritten 分页列表 |

---

## 六、顺序小结

1. **新建批次**：调用 execute 接口 → 写 `pipeline_rewritten_batches` 一条 + `pipeline_data_items_rewritten` 多条（status=init）。
2. **在批次中运行**：调用 run 接口 → 该批次下 init/processing 记录入队，等待消费者拉取。
3. **生成 pipeline_data_items_rewritten 数据**：消费者取任务 → 占位 processing → run_one_rewritten → Flow(rewritten_data_service_agent) → update_rewritten_data_func 更新同一条记录为 success（或 failed），完成单条「数据清洗」结果落库。

整体为「先建批次与 init 记录，再按批次入队，由后台消费者异步执行并写回改写结果」的异步链路。
