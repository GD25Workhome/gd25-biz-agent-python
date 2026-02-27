# Rewritten 流程批量异步执行技术设计

## 1. 概述

### 1.1 背景

当前 `rewritten_service.py` 的 `execute_rewritten` 为**同步执行**：用户发起请求后，后端查询待处理任务、依次执行改写流程，直至全部完成才返回。对于大批量数据，会导致请求超时、用户长时间等待。

### 1.2 目标

将流程改为**批量创建 + 异步轮询执行**模式：

1. **接口阶段**：快速创建改写任务批次，写入 `pipeline_data_items_rewritten` 表，并立即返回 `batch_code` 和任务总数。
2. **后台阶段**：独立进程/任务持续扫描表中 `status=init` 的记录，逐个执行改写流程并更新状态。

### 1.3 方案选型（本项目）

- **后台 Worker**：采用 **方案一（FastAPI lifespan + asyncio 后台循环）**。
- **适用说明**：本项目为 demo 验证系统，暂不考虑 Celery、arq 等复杂队列方案，部署简单、无额外依赖即可满足需求。

---

## 2. 数据结构变更

### 2.1 DataItemsRewrittenRecord 模型

**文件**：`backend/infrastructure/database/models/data_items_rewritten.py`

| 字段 | 变更说明 |
|------|----------|
| `status` | 新增 `init`（刚初始化）、`processing`（执行中）；原取值 `success` / `failed` 保留。 |

**状态流转**：`init` → `processing` → `success` / `failed`（采用子方案 B 时）

### 2.2 初始化记录字段

创建批次时，每条初始化记录需包含：

| 字段 | 取值说明 |
|------|----------|
| `source_dataset_id` | 来源 `dataSets.id`（关联 data_sets_items.dataset_id） |
| `source_item_id` | 来源 `dataItems.id`（关联 data_sets_items.id） |
| `status` | `init` |
| `batch_code` | 批次编码，同一批次统一为：`YYYYMMDDHHmmss`（如 `20260210143025`） |

其他业务字段（如 `scenario_description`、`rewritten_question` 等）创建时可为空，由后续执行流程填充。

---

## 3. 阶段一：批量创建改写任务

### 3.1 流程说明

1. 根据 `item_ids` 或 `query_params` 查询 `pipeline_data_sets_items`，得到待处理 `records`。
2. 生成 `batch_code = datetime.now().strftime("%Y%m%d%H%M%S")`。
3. 对每条 `record` 在 `pipeline_data_items_rewritten` 中创建一条记录：
   - `source_dataset_id` = `record.dataset_id`
   - `source_item_id` = `record.id`
   - `status` = `init`
   - `batch_code` = 上述统一值
4. 返回 `batch_code` 与 `total`（创建任务数）。

### 3.2 接口返回值变更

**原**：`RewrittenExecuteStats(total, success, failed)`

**新**：`RewrittenBatchCreateResult(batch_code, total)`

```python
@dataclass
class RewrittenBatchCreateResult:
    """批量创建改写任务结果"""
    batch_code: str      # 批次编码
    total: int           # 创建的任务总数
```

### 3.3 涉及文件

| 文件 | 修改内容 |
|------|----------|
| `backend/pipeline/rewritten_service.py` | 新增 `create_rewritten_batch`，修改 `execute_rewritten` 逻辑或拆分 |
| `backend/infrastructure/database/repository/data_items_rewritten_repository.py` | 新增 `create_init_records_batch` 或类似方法 |
| `backend/app/api/schemas/data_cleaning.py` | 新增 `RewrittenBatchCreateResult`，调整 `RewrittenExecuteResponse` |
| `backend/app/api/routes/data_cleaning.py` | 使用新返回结构 |

---

## 4. 阶段二：异步轮询执行 —— 方案设计

后台需持续扫描 `status=init` 的记录并执行改写流程。以下为多套 Python 实现方案，供选型参考。

### 4.1 方案一：FastAPI lifespan + asyncio 后台循环（轻量级）【本项目采用】

**思路**：在应用启动时注册一个后台协程，在独立 `asyncio.Task` 中循环拉取 `init` 任务并执行。

**优点**：

- 无额外依赖，与现有 FastAPI 架构一致
- 部署简单，无需单独进程

**缺点**：

- 与主进程同生命周期，进程重启即停止
- 无法水平扩展（多实例会重复消费）
- 无任务持久化队列，依赖数据库作为「队列」

**适用**：单实例、任务量中等、可接受进程重启后继续从数据库拉取。适合 demo 验证系统。

**实现要点**：

```python
# main.py lifespan
async def rewritten_worker_loop():
    while True:
        async with session_factory() as session:
            records = await repo.get_init_records(limit=10)
            for rec in records:
                await run_one_rewritten(rec, session)
        await asyncio.sleep(2)  # 轮询间隔
```

---

### 4.2 方案二：APScheduler 定时任务（项目已依赖）

**思路**：使用 APScheduler 定时（如每 10 秒）执行一次「拉取 init 并执行」的逻辑。

**优点**：

- 项目已有 `APScheduler==3.11.1` 依赖
- 配置灵活：间隔、cron 表达式均可调
- 可与 FastAPI 生命周期集成

**缺点**：

- 固定间隔，无法做到「有任务立刻执行」
- 多实例部署时需注意避免重复执行（可通过分布式锁或单实例调度解决）

**适用**：任务量不大、可接受一定延迟、希望与现有调度体系统一。

**实现要点**：

```python
# 注册 job
scheduler.add_job(
    poll_and_run_rewritten,
    'interval',
    seconds=10,
    id='rewritten_worker'
)
```

---

### 4.3 方案三：Celery 异步任务队列（项目已依赖）

**思路**：将「执行单条改写」封装为 Celery task，由 Worker 消费。创建批次后，可批量 `delay` 多个 task，或由定时 task 拉取 `init` 并 `delay`。

**优点**：

- 项目已有 `celery==5.6.0` 依赖
- 支持多 Worker、水平扩展、任务持久化
- 支持重试、超时、优先级

**缺点**：

- 需 Redis/RabbitMQ 等 Broker，部署和运维复杂度增加
- 需要单独启动 Celery Worker 进程

**适用**：生产环境、任务量大、需要可靠队列与扩展能力。

**实现要点**：

```python
@celery_app.task
def run_rewritten_task(rewritten_record_id: str):
    # 获取 record，查 data_sets_items，执行 _run_one
    ...

# 创建批次后
for rec in init_records:
    run_rewritten_task.delay(rec.id)
```

---

### 4.4 方案四：arq（Redis + asyncio 任务队列）

**思路**：使用 arq 作为异步任务队列，Worker 为 asyncio，与现有 `async/await` 风格一致。

**优点**：

- 原生 asyncio，与 SQLAlchemy 异步会话、`_run_one` 等无缝集成
- 支持 Redis 持久化与重试
- 比 Celery 更轻量

**缺点**：

- 新增依赖与 Redis
- 需单独启动 arq Worker

**适用**：希望保持全异步、又需要队列能力。

---

### 4.5 方案五：PostgreSQL LISTEN/NOTIFY 事件驱动

**思路**：创建批次后，执行 `NOTIFY rewritten_new_batch`；Worker 进程 `LISTEN` 该频道，收到通知后立即拉取 `init` 任务并执行。

**优点**：

- 无额外中间件，复用现有 PostgreSQL
- 事件驱动，响应及时

**缺点**：

- 需要常驻监听进程
- 通知不持久化，进程重启会丢失期间通知（可通过启动时全量扫描 init 弥补）

**适用**：已有 PostgreSQL、不想引入 Redis/消息队列。

---

### 4.6 方案对比小结

| 方案 | 额外依赖 | 部署复杂度 | 扩展性 | 适用场景 |
|------|----------|------------|--------|----------|
| 一、lifespan + asyncio | 无 | 低 | 单实例 | 开发/小规模 |
| 二、APScheduler | 无（已有） | 低 | 中（需分布式锁） | 中等规模、定时轮询 |
| 三、Celery | Redis/RabbitMQ（已有依赖） | 中 | 高 | 生产、大批量 |
| 四、arq | Redis | 中 | 高 | 生产、全异步 |
| 五、PG LISTEN/NOTIFY | 无 | 中 | 中 | 已有 PG、轻量事件驱动 |

---

## 5. 阶段三：单条任务执行逻辑

### 5.1 执行流程

对每条 `status=init` 的 `DataItemsRewrittenRecord`：

1. 根据 `source_dataset_id`、`source_item_id` 在 `pipeline_data_sets_items` 中查询 `DataSetsItemsRecord`。
2. 若查不到，则更新该 rewritten 记录为 `status=failed`，`execution_metadata` 记录原因。
3. 若查到，则调用 `_run_one(record, dataset_id, graph)` 执行改写流程。
4. 流程结束后，由 `update_rewritten_data_func` 将结果写回 `pipeline_data_items_rewritten`，并更新 `status=success` 或 `status=failed`。

### 5.2 insert_rewritten_data_func 升级为 update_rewritten_data_func

在新模式下，批次创建时已在 `pipeline_data_items_rewritten` 中预创建 `status=init` 的记录，flow 执行结束后应**更新**已有记录而非新建。因此需将原 `insert_rewritten_data_func` 升级为 `update_rewritten_data_func`。

#### 5.2.1 逻辑变更

| 项目 | 原逻辑 | 新逻辑 |
|------|--------|--------|
| 方法名 | `insert_rewritten_data_func` | `update_rewritten_data_func` |
| 核心操作 | 根据 source_dataset_id + source_item_id 查找，存在则 update、否则 create | **仅 update**：根据 source_dataset_id + source_item_id 查找已有 init 记录并更新 |
| 前提 | 无 | 调用前记录已存在（由批次创建阶段预写入） |

#### 5.2.2 实现变更

| 文件 | 修改内容 |
|------|----------|
| `backend/domain/flows/implementations/insert_rewritten_data_func.py` | 重命名为 `update_rewritten_data_func.py`；类名 `InsertRewrittenDataNode` → `UpdateRewrittenDataNode`；`get_key()` 返回 `"update_rewritten_data_func"`；`execute` 内改为 `repo.update(...)` 或先 `get_by_source_dataset_and_item_id` 再 `update` |
| `backend/domain/flows/implementations/__init__.py` | 导入 `UpdateRewrittenDataNode`（继承 `BaseFunctionNode` 时自动注册，`get_key()` 返回 `"update_rewritten_data_func"`） |
| `config/flows/pipeline_step2/flow.yaml` | 节点名 `insert_rewritten_data_node` → `update_rewritten_data_node`；`function_key` → `"update_rewritten_data_func"`；edges 中的 `from`/`to` 同步改为 `update_rewritten_data_node` |

#### 5.2.3 flow.yaml 变更示例

```yaml
# 原
nodes:
  - name: insert_rewritten_data_node
    type: function
    config:
      function_key: "insert_rewritten_data_func"

edges:
  - from: rewritten_agent_node
    to: insert_rewritten_data_node
  - from: insert_rewritten_data_node
    to: END

# 新
nodes:
  - name: update_rewritten_data_node
    type: function
    config:
      function_key: "update_rewritten_data_func"

edges:
  - from: rewritten_agent_node
    to: update_rewritten_data_node
  - from: update_rewritten_data_node
    to: END
```

#### 5.2.4 Repository 补充

`DataItemsRewrittenRepository` 需新增按 `source_dataset_id` + `source_item_id` 查询单条的方法（若仅有 `get_by_source_item_id` 则需扩展）：

```python
async def get_by_source_ids(
    self,
    source_dataset_id: str,
    source_item_id: str,
) -> Optional[DataItemsRewrittenRecord]:
    """按 source_dataset_id + source_item_id 查询单条。"""
```

### 5.3 方案一内部：拉取与防重机制设计

方案一为单进程、单 Worker，不存在多实例抢同一批记录的问题。但在单进程内部，拉取 `init` 任务时仍有多种实现方式，每种对「重复执行」「崩溃恢复」有不同影响。以下拆解三种子方案。

#### 5.3.1 子方案 A：直接拉取 init，串行执行，无中间态

**流程**：`SELECT ... WHERE status='init' LIMIT N` → 逐条 `await run_one_rewritten(rec)`。

| 项目 | 说明 |
|------|------|
| 实现 | 最简单，无需改模型、无锁 |
| 重复执行风险 | 若某条执行中进程崩溃，该记录仍为 init，下次循环会再次被拉取并执行 |
| 幂等性 | 依赖 `update_rewritten_data_func` 的 update 逻辑：对同一 source 的多次写入最终以最后一次为准，通常可接受 |
| 适用 | demo、可接受极少重复执行的场景 |

#### 5.3.2 子方案 B：借助中间态 processing，并行执行（推荐）【本项目采用】

**流程**：拉取 init → 立即将 `status` 更新为 `processing` → **并行**执行多条 `_run_one`（Semaphore 限流）→ 执行完成后由 flow 内 `update_rewritten_data_func` 将 `status` 更新为 `success`/`failed`。

| 项目 | 说明 |
|------|------|
| 实现 | 需在模型中新增 `status='processing'`；拉取后先 `UPDATE ... SET status='processing'` 再执行 |
| 重复执行风险 | 低。已标记为 processing 的记录不会再次被拉取 |
| 崩溃恢复 | 进程崩溃后，processing 记录不会被自动重试；可增加定时任务将「长时间处于 processing」的记录回滚为 init 以供重试（可选，demo 可暂不实现） |
| 状态流转 | `init` → `processing` → `success`/`failed` |
| 适用 | 希望语义清晰、便于排查「执行中」任务 |

**模型变更**：`status` 注释补充 `processing`（执行中）。

---

##### 5.3.2.1 子方案 B 实现细节

**执行模式**：**并行**。每轮拉取一批 init 记录后，使用 `asyncio.gather` + `Semaphore` 限流并发执行，与现有 `_run_batch_parallel` 一致。

###### 常量与配置

```python
# rewritten_service.py 或独立 worker 模块
STATUS_INIT = "init"
STATUS_PROCESSING = "processing"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"

# Worker 配置
POLL_INTERVAL_SECONDS = 2   # 轮询间隔（秒）
BATCH_SIZE = 10             # 每轮拉取条数
MAX_CONCURRENT = 4          # 最大并发数（同时执行的 run_one 数量）
```

###### 拉取与更新为 processing 的时序

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | `get_init_records(limit=BATCH_SIZE)` | 仅查询 `status=init`，按 `created_at` 升序，保证先进先出 |
| 2 | 对每条 record：`update_status(rec.id, STATUS_PROCESSING)` | 拉取后立即在同一 session 内批量更新，commit 后再执行，避免执行中崩溃导致重复拉取 |
| 3 | `asyncio.gather(*[run_with_semaphore(rec) for rec in records])` | **并行**执行改写流程，通过 Semaphore 限制最大并发数为 MAX_CONCURRENT；每条内部新建 session，调用 `_run_one` → graph.ainvoke → update_rewritten_data_func |
| 4 | 若步骤 2 或 3 异常 | 使用 `gather(..., return_exceptions=True)` 收集各任务结果，对异常/失败的 record 手动 `update_status(rec.id, STATUS_FAILED, execution_metadata)` |

###### Repository 方法

**get_init_records**：只拉取 `status=init`，不包含 processing。

```python
async def get_init_records(
    self,
    limit: int = 10,
    batch_code: Optional[str] = None,
) -> List[DataItemsRewrittenRecord]:
    """
    拉取 status=init 的记录。
    按 created_at 升序，保证先进先出。
    """
    stmt = (
        select(DataItemsRewrittenRecord)
        .where(DataItemsRewrittenRecord.status == STATUS_INIT)
        .order_by(DataItemsRewrittenRecord.created_at.asc())
        .limit(limit)
    )
    if batch_code:
        stmt = stmt.where(DataItemsRewrittenRecord.batch_code == batch_code)
    result = await self.session.execute(stmt)
    return list(result.scalars().all())
```

**update_status**：更新单条记录的 status（及可选的 execution_metadata）。需从 `sqlalchemy` 导入 `update`。

```python
from sqlalchemy import update

async def update_status(
    self,
    record_id: str,
    status: str,
    execution_metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """更新记录的 status，失败时可选写入 execution_metadata。"""
    stmt = (
        update(DataItemsRewrittenRecord)
        .where(DataItemsRewrittenRecord.id == record_id)
        .values(status=status, execution_metadata=execution_metadata)
    )
    result = await self.session.execute(stmt)
    return result.rowcount > 0
```

###### Worker 主循环伪代码

```python
async def rewritten_worker_loop() -> None:
    """子方案 B（并行）：拉取 init → 更新 processing → 并行执行 → 由 update_rewritten_data_func 更新为 success/failed"""
    session_factory = get_session_factory()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def run_with_semaphore(rec: DataItemsRewrittenRecord) -> tuple[str, bool, Optional[Exception]]:
        """在 semaphore 限制下执行单条，返回 (record_id, success, exception)。"""
        async with semaphore:
            try:
                await run_one_rewritten(rec)
                return (rec.id, True, None)
            except Exception as e:
                return (rec.id, False, e)

    while True:
        try:
            async with session_factory() as session:
                repo = DataItemsRewrittenRepository(session)
                records = await repo.get_init_records(limit=BATCH_SIZE)
                if not records:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # 2. 批量更新为 processing，commit 后释放 session
                updated_records = []
                for rec in records:
                    try:
                        ok = await repo.update_status(rec.id, STATUS_PROCESSING)
                        if ok:
                            updated_records.append(rec)
                    except Exception as e:
                        await session.rollback()
                        logger.exception("更新 status=processing 失败 record_id=%s", rec.id)
                        updated_records = []  # 出现异常则本批次不执行
                        break
                await session.commit()
                records = updated_records

                if not records:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # 3. 并行执行（每条内部使用独立 session，semaphore 限流）
                results = await asyncio.gather(
                    *[run_with_semaphore(rec) for rec in records],
                    return_exceptions=True,
                )

                # 4. 对异常/失败的 record 手动更新为 failed
                for i, res in enumerate(results):
                    rec = records[i]
                    if isinstance(res, Exception):
                        # 协程抛出未捕获异常（极少见）
                        _mark_failed(session_factory, rec.id, str(res))
                    elif isinstance(res, tuple) and not res[1] and res[2]:  # (record_id, success, exception)
                        _mark_failed(session_factory, rec.id, str(res[2]))

        except Exception as e:
            logger.exception("rewritten_worker_loop 异常: %s", e)

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _mark_failed(session_factory, record_id: str, reason: str) -> None:
    """将 record 标记为 failed。"""
    async with session_factory() as s:
        repo = DataItemsRewrittenRepository(s)
        await repo.update_status(record_id, STATUS_FAILED, {"failure_reason": reason, "stage": "run_one"})
        await s.commit()
```

###### run_one_rewritten 职责

`run_one_rewritten(rec: DataItemsRewrittenRecord)` 需实现：

1. 根据 `rec.source_dataset_id`、`rec.source_item_id` 查询 `DataSetsItemsRecord`。
2. 若查不到：更新该 rewritten 记录为 `status=failed`，`execution_metadata` 记录「来源数据不存在」。
3. 若查到：调用 `_run_one(record, dataset_id, graph)`。flow 结束后，`update_rewritten_data_func` 会根据 `source_dataset_id` + `source_item_id` 找到该记录并更新为 `success` 或 `failed`。

**注意**：

- `run_one_rewritten` 内部应使用**独立 session**，不共享 Worker 拉取时的 session，避免长事务与 session 混用。
- 多个 `run_one_rewritten` 可**并行**执行，Semaphore 限制同时运行的数量为 `MAX_CONCURRENT`，每个任务独立 session、互不干扰。

###### 异常与边界

| 场景 | 处理方式 |
|------|----------|
| 更新 processing 失败 | 记录日志，跳过该条，其余照常执行 |
| `_run_one` 抛异常（未走到 update_rewritten_data_func） | `run_with_semaphore` 捕获后返回 `(id, False, e)`，Worker 遍历 results 时调用 `_mark_failed` |
| 查不到 data_sets_items | 在 `run_one_rewritten` 内更新为 failed，不调用 `_run_one` |
| 某条任务失败 | 并行下其他任务不受影响，`gather(return_exceptions=True)` 保证所有任务完成后再统一处理失败项 |
| 进程重启 | 下次循环从 DB 重新拉取 init；原 processing 记录保持不动（demo 可暂不做超时回滚） |

#### 5.3.3 子方案 C：SELECT FOR UPDATE SKIP LOCKED

**流程**：`SELECT ... WHERE status='init' ... FOR UPDATE SKIP LOCKED LIMIT N`，在同一事务内执行，执行完成后再 commit，从而在数据库层面锁定行。

| 项目 | 说明 |
|------|------|
| 实现 | 需在 `get_init_records` 中加 `with_for_update(skip_locked=True)`，且在**同一 session 内**完成「拉取 + 执行 + 更新 status」，事务结束后才释放锁 |
| 重复执行风险 | 极低，行级锁保证同一时刻只有当前 Worker 能处理该行 |
| 注意 | `_run_one` 内会启动新的 session（如 `insert_rewritten_data_func` 内），若拉取与执行跨 session，需在拉取 session 中先将 status 改为 processing 或直接改为 success/failed 占位，否则锁会过早释放 |
| 适用 | 对一致性要求高、希望利用数据库锁 |

#### 5.3.4 子方案对比

| 子方案 | 复杂度 | 防重能力 | 崩溃恢复 | 推荐场景 |
|--------|--------|----------|----------|----------|
| A. 无中间态 | 低 | 依赖幂等 | 自动重试 | 极简 demo |
| B. 中间态 processing | 中 | 高 | 需额外逻辑回滚 processing | **推荐**，demo 验证系统 |
| C. FOR UPDATE SKIP LOCKED | 中高 | 极高 | 依赖事务边界 | 强一致性场景 |

**本项目建议**：采用 **子方案 B（中间态 processing）**，状态语义清晰，便于后续扩展「超时回滚」等能力；demo 阶段可不实现超时回滚。

---

## 6. 数据流概览

```
用户请求 (item_ids / query_params)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│ 1. 查询 pipeline_data_sets_items                         │
│ 2. 生成 batch_code = YYYYMMDDHHmmss                      │
│ 3. 批量创建 pipeline_data_items_rewritten（status=init）  │
│ 4. 返回 batch_code + total                               │
└─────────────────────────────────────────────────────────┘
        │
        │  （用户立即得到响应）
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│ 后台 Worker（方案一：lifespan + asyncio，子方案 B 并行）   │
│   - 扫描 status=init 的记录，拉取后置 processing          │
│   - asyncio.gather + Semaphore 限流并行执行               │
│   - 每条：按 source_dataset_id + source_item_id 查 data_sets_items │
│   - 调用 _run_one → graph.ainvoke → update_rewritten_data_func │
│   - 更新 status=success/failed                           │
└─────────────────────────────────────────────────────────┘
```

---

## 7. API 变更汇总

### 7.1 请求

保持不变：`POST /data-cleaning/datasets/{dataset_id}/items/rewritten/execute`，body 为 `RewrittenExecuteRequest`（`item_ids` 或 `query_params`）。

### 7.2 响应

**原**：

```json
{
  "success": true,
  "message": "数据清洗完成",
  "stats": { "total": 100, "success": 95, "failed": 5 }
}
```

**新**：

```json
{
  "success": true,
  "message": "批次已创建，任务将异步执行",
  "batch_code": "20260210143025",
  "total": 100
}
```

前端可依据 `batch_code` 查询 `GET /data-cleaning/data-items-rewritten?batch_code=xxx` 获取执行进度（通过 `status` 分布统计）。

---

## 8. 实施建议与顺序

1. **模型与仓储**：在 `DataItemsRewrittenRecord` 中确认 `status` 支持 `init`、`processing`，新增批量创建方法及 `get_by_source_ids`。
2. **update_rewritten_data_func 升级**：将 `insert_rewritten_data_func` 重命名为 `update_rewritten_data_func`，逻辑改为仅 update；同步修改 flow.yaml 节点名与 function_key；更新 `implementations/__init__.py` 导入。
3. **服务层**：实现 `create_rewritten_batch`，替换原 `execute_rewritten` 的同步执行逻辑。
4. **API 层**：调整 `RewrittenExecuteResponse` 与路由返回。
5. **Worker 实现**：采用方案一（lifespan + asyncio），子方案 B（processing 中间态，**并行**执行），在 main.py lifespan 中启动 `rewritten_worker_loop`；使用 `asyncio.gather` + `Semaphore(MAX_CONCURRENT)` 限流；Repository 新增 `update_status`；实现 `run_one_rewritten(rec)`（查 data_sets_items → 调 `_run_one`，异常时由 Worker 统一 `_mark_failed`）。
6. **测试**：覆盖批次创建、状态流转、update 逻辑正确性。

---

## 9. 附录：Repository 接口补充

### 9.1 DataItemsRewrittenRepository

```python
async def create_init_batch(
    self,
    records: List[DataSetsItemsRecord],
    batch_code: str,
    dataset_id: str,
) -> int:
    """批量创建 init 记录，返回创建数量。"""
    ...

async def get_init_records(
    self,
    limit: int = 10,
    batch_code: Optional[str] = None,
) -> List[DataItemsRewrittenRecord]:
    """拉取 status=init 的记录，按 created_at 升序。子方案 B 下，拉取后由 Worker 调用 update_status 置为 processing。"""
    ...

async def update_status(
    self,
    record_id: str,
    status: str,
    execution_metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """更新记录的 status，失败时可写入 execution_metadata。"""
    ...

async def get_by_source_ids(
    self,
    source_dataset_id: str,
    source_item_id: str,
) -> Optional[DataItemsRewrittenRecord]:
    """按 source_dataset_id + source_item_id 查询单条，供 update_rewritten_data_func 使用。"""
    ...
```

### 9.2 DataSetsItemsRepository

已有 `get_by_ids`，可直接使用。若按单条 `source_item_id` 查询，可新增：

```python
async def get_by_dataset_and_item_id(
    self,
    dataset_id: str,
    item_id: str,
) -> Optional[DataSetsItemsRecord]:
    """按 dataset_id + item_id 查询单条。"""
    ...
```

---

## 10. 开发完成情况

| 任务 | 状态 | 说明 |
|------|------|------|
| 1. 模型与仓储 | ✅ 已完成 | `status` 注释补充 init/processing；DataItemsRewrittenRepository 新增 create_init_batch、get_init_records、update_status、get_by_source_ids；DataSetsItemsRepository 新增 get_by_dataset_and_item_id |
| 2. update_rewritten_data_func | ✅ 已完成 | 新建 `update_rewritten_data_func.py`，UpdateRewrittenDataNode；flow.yaml 改为 update_rewritten_data_node；implementations/__init__.py 导入 UpdateRewrittenDataNode |
| 3. 服务层 | ✅ 已完成 | create_rewritten_batch、run_one_rewritten、rewritten_worker_loop、_mark_failed 已实现 |
| 4. API 层 | ✅ 已完成 | RewrittenExecuteResponse 改为 batch_code + total；execute_rewritten_endpoint 调用 create_rewritten_batch |
| 5. Worker 启动 | ✅ 已完成 | main.py lifespan 中 asyncio.create_task(rewritten_worker_loop())，关闭时 cancel |
| 6. 前端 | ✅ 已完成 | pipeline_dataset_items.js 适配新响应格式，提示 batch_code 与 total |

---

*文档版本：1.0*  
*创建日期：2026-02-10*
