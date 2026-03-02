# 批次任务（batch_jobs）与 Step02 清洗批次管理功能对比与缺口分析

## 1. 文档目的

- 整理「Step02 清洗批次管理」的基础功能清单，作为通用批次管理界面的参考。
- 对比当前 `backend/app/api/routes/batch_jobs.py` 模块能力，列出为做成类 Step02 清洗批次管理界面尚缺的功能。

**参考文档**：`cursor_docs/021103-Step02清洗批次管理技术设计.md`、`021105-Step02批次任务队列与运行停止技术设计.md`。

---

## 2. Step02 清洗批次管理 基础功能整理

### 2.1 数据与模型

| 项目 | 说明 |
|------|------|
| 批次表 | `RewrittenBatchRecord`（rewritten_batch），字段：batch_code、total_count、create_params、status、created_at、updated_at |
| 子项表 | `DataItemsRewrittenRecord`（pipeline_data_items_rewritten），通过 batch_code 关联 |
| 子项状态 | init / processing / success / failed |

### 2.2 后端 API 清单

| # | 方法 | 路径 | 功能说明 |
|---|------|------|----------|
| 1 | GET | `/data-cleaning/rewritten-batches` | 批次列表：含元数据 + 统计（data_items_total、status_init/processing/success/failed_count） |
| 2 | POST | `/data-cleaning/rewritten-batches/run` | 按 batch_code 将该批次下待处理/执行中的任务入队 |
| 3 | POST | `/data-cleaning/rewritten-batches/clear-queue` | 清空全部队列（模式 1） |
| 4 | POST | `/data-cleaning/rewritten-batches/remove-batch` | 从队列中移除当前批次（模式 2） |
| 5 | GET | `/data-cleaning/rewritten-batches/queue-stats` | 队列统计：排队数、执行中+排队总数 |

**列表查询参数**：`batch_code`（模糊）、`limit`、`offset`。

### 2.3 前端界面能力（PipelineRewrittenBatchesComponent）

| # | 能力 | 说明 |
|---|------|------|
| 1 | 菜单与 Tab | 侧边栏「Step02清洗批次管理」独立 Tab |
| 2 | 查询区 | batch_code（包含）、查询 / 重置、可折叠 |
| 3 | 表格列 | batch_code、预期总数、实际数据量、待处理/执行中/成功/失败计数、批次状态、创建时间、更新时间 |
| 4 | 操作列 | 运行、移除队列（每行） |
| 5 | 顶部操作 | 「清空队列」按钮 |
| 6 | 分页 | limit 可选、offset 分页、显示总条数 |

---

## 3. 当前 batch_jobs 模块能力

### 3.1 路由与数据模型

- **路由前缀**：`/api/v1/batch-jobs`
- **批次表**：`BatchJobRecord`（batch_job），字段：id、job_type、code、total_count、query_params、create_time、update_time 等
- **子任务表**：`BatchTaskRecord`（batch_task），通过 job_id 关联；状态：pending / running / success / failed

### 3.2 已有 API

| # | 方法 | 路径 | 功能说明 |
|---|------|------|----------|
| 1 | POST | `/batch-jobs/create` | 通用批次创建（job_type + query_params），返回 batch_code、total |
| 2 | POST | `/batch-jobs/{job_id}/run` | 将指定 job 下 status=pending 的 batch_task 入队，返回 enqueued 数量 |

### 3.3 队列服务（batch_task_queue_service）

- `enqueue_batch_by_job_id(job_id, session)`：按 job_id 入队。
- `get_queue_stats()`：返回 queue_size、in_flight_count（当前未暴露为 HTTP 接口）。
- **无**：clear_all、remove_batch_by_job_id 等类似 Step02 的队列操作。

---

## 4. batch_jobs 相对 Step02 的缺口（待开发）

### 4.1 后端 API 缺口

| # | 能力 | Step02 对应 | 说明 |
|---|------|-------------|------|
| 1 | 批次列表（含统计） | GET /rewritten-batches | 需新增 GET `/batch-jobs` 或 GET `/batch-jobs/list`：返回批次列表 + 每批次下 batch_task 的 total、status_pending_count、status_running_count、status_success_count、status_failed_count；支持 batch_code、job_type 等筛选与 limit/offset |
| 2 | 列表查询与分页 | batch_code 模糊、limit、offset | BatchJobRepository 已有 get_list(limit, offset)，但无 batch_code/job_type 筛选，无与 batch_task 的聚合统计 |
| 3 | 清空队列 | POST /rewritten-batches/clear-queue | 需在 batch_task_queue_service 中实现 clear_all_queue，并暴露 POST `/batch-jobs/clear-queue`（或等价路径） |
| 4 | 按批次移除队列 | POST /rewritten-batches/remove-batch | 需实现 remove_batch_by_job_id(job_id)，并暴露 POST `/batch-jobs/remove-batch`（body 含 job_id） |
| 5 | 队列统计 | GET /rewritten-batches/queue-stats | 需暴露 GET `/batch-jobs/queue-stats`，返回 get_queue_stats() 的结果（queue_size、in_flight_count 等） |

### 4.2 仓储层缺口

| # | 能力 | 说明 |
|---|------|------|
| 1 | 列表筛选 | BatchJobRepository.get_list 增加可选参数：code（模糊）、job_type（精确）等 |
| 2 | 带统计的列表 | 新增 get_jobs_with_stats(code?, job_type?, limit, offset)：基于 batch_job 左联 batch_task 按 status 聚合，返回 (List[BatchJobWithStatsDTO], total) |

### 4.3 前端缺口

| # | 能力 | 说明 |
|---|------|------|
| 1 | 独立入口 | 在合适的一级/二级菜单下增加「批次任务管理」或「通用批次管理」菜单项与 Tab（入口页面需根据项目现有结构确定，如独立 html 或嵌入现有 pipeline 页） |
| 2 | 列表页组件 | 新组件：查询区（batch_code、job_type 等）、表格（job 元数据 + 四态统计）、分页 |
| 3 | 操作列 | 每行：「运行」（调用 POST /batch-jobs/{job_id}/run）、「移除队列」（调用 remove-batch，传 job_id） |
| 4 | 顶部操作 | 「清空队列」按钮（调用 clear-queue） |
| 5 | 队列统计展示 | 可选：在列表页顶部或侧边展示 queue-stats（排队数、执行中等） |

### 4.4 小结：batch_jobs 缺什么

- **已有**：创建批次、按 job_id 运行（入队）。
- **缺少**：  
  - 批次列表（含子任务统计）与查询分页；  
  - 清空队列、按 job 移除队列、队列统计 的 API 与前端；  
  - 类 Step02 的「批次管理」完整前端页（菜单 + 列表 + 操作列 + 分页）。

---

## 5. 建议实现顺序

1. **后端**  
   - 队列：在 `batch_task_queue_service` 中实现 clear_all、remove_batch_by_job_id（若尚未有）；暴露 queue-stats、clear-queue、remove-batch 的 HTTP 接口。  
   - 仓储：BatchJobRepository 增加 get_jobs_with_stats（code、job_type、limit、offset）。  
   - 路由：在 batch_jobs 路由中增加 GET list、GET queue-stats、POST clear-queue、POST remove-batch。
2. **前端**  
   - 新增「批次任务管理」菜单与 Tab、列表组件（查询 + 表格 + 分页）、操作列（运行、移除队列）及顶部「清空队列」、可选 queue-stats 展示。
3. **联调与测试**  
   - 列表筛选与统计正确性、入队/清空/移除与 queue-stats 一致性。

---

## 6. 参考文件索引

| 文件 | 说明 |
|------|------|
| backend/app/api/routes/batch_jobs.py | 当前批次任务路由（仅 create、run） |
| backend/app/api/routes/data_cleaning.py | Step02 清洗批次管理 API（列表、run、clear、remove、queue-stats） |
| frontend/js/pipeline_rewritten_batches.js | Step02 清洗批次管理前端组件 |
| backend/infrastructure/database/repository/batch/batch_job_repository.py | 批次表仓储（当前无带统计的列表） |
| backend/pipeline/batch_task_queue_service.py | 通用 batch_task 队列（有 get_queue_stats，无 clear/remove 对外） |
| cursor_docs/021103-Step02清洗批次管理技术设计.md | Step02 批次管理列表与统计设计 |
| cursor_docs/021105-Step02批次任务队列与运行停止技术设计.md | Step02 运行/清空/移除三种模式 |

---

## 7. 开发进度（按 030202 缺口实现）

| # | 项目 | 状态 | 说明 |
|---|------|------|------|
| 1 | 队列服务 clear_all_queue、remove_batch_by_job_id | ✅ 已完成 | `backend/pipeline/batch_task_queue_service.py` |
| 2 | BatchJobRepository get_list 筛选（code、job_type）、get_jobs_with_stats | ✅ 已完成 | `backend/infrastructure/database/repository/batch/batch_job_repository.py`，含 BatchJobStatsRow |
| 3 | batch_jobs Schema（列表/队列 请求与响应） | ✅ 已完成 | `backend/app/api/schemas/batch_jobs.py` |
| 4 | 路由 GET list、GET queue-stats、POST clear-queue、POST remove-batch | ✅ 已完成 | `backend/app/api/routes/batch_jobs.py` |
| 5 | 前端：批次任务管理菜单 + Tab + 组件 | ✅ 已完成 | data-cleaning 新增「批次任务管理」菜单；`frontend/js/pipeline_batch_jobs.js`；`pipeline_common.js` 增加 BATCH_JOBS_API_PREFIX |

**文档编号**：030202；基于 Step02 清洗批次管理功能整理，对比 batch_jobs 模块并列出缺口与实现顺序建议。
