# 批次任务执行 Session 拆分改造技术方案

## 1. 背景与问题

### 1.1 当前流程

消费者侧（`batch_task_queue_service._consumer_loop`）对每条任务：

1. 使用 **一个** `async with session_factory() as session` 包住整次执行；
2. 调用 `execute_service.run_one_batch_task(session, item)`；
3. 模版内部依次：
   - **阶段 1**：`update_status_to_running_if_pending(task_id)`（pending → running）；
   - **阶段 2**：`execute_task_impl(session, task_record)`（业务实现，可能很耗时）；
   - **阶段 3**：`update_status(task_id, status=success/failed, ...)`（结果回写）；
4. 最后在消费者里 `await session.commit()`。

即：**同一个 DB session（及背后连接、事务）贯穿三个阶段**。

### 1.2 问题

当阶段 2（`execute_task_impl`）耗时长时（如调用外部 API、大模型、Embedding、重计算等）：

- **连接占用过长**：该连接在整个执行期间被占用，多消费者并发时易占满连接池或拖慢其他请求。
- **事务时间过长**：事务从第一次写一直延续到最终 commit，锁/快照保留时间被拉长，易产生锁等待、死锁或事务超时。
- **资源浪费**：阶段 2 多数情况下不依赖本次 session 的 DB 状态，长时间持有 session 没有必要。

---

## 2. 改造目标

- **Session 与“长时间业务”解耦**：仅在两次“短 DB 操作”时使用 session，中间长时间业务不持有同一 session。
- **两段短 Session**：
  - **Session 1**：加载 task、version 校验、pending → running 更新，commit 后即关闭；
  - **阶段 2**：执行 `execute_task_impl`，**不传入** 上述 session（若业务需要 DB，由实现方自行开短 session）；
  - **Session 2**：根据结果更新 status（success/failed）及 execution_result/execution_error_message，commit 后关闭。
- **对外接口尽量保持**：调用方（队列消费者）仍只需传“能创建 session 的工厂”或等价能力，不关心内部两段 session 的细节。

---

## 3. 方案概述

### 3.1 核心思路

- 消费者**不再**为整次执行持有一个长 session，改为传入 **session 工厂**（如 `get_session_factory()` 的返回值）。
- `BatchTaskExecuteService.run_one_batch_task` 和 `ExecuteTemplate.run_one_task` 改为接收 **session 工厂**（或在使用处通过工厂自行创建 session），在模版内部：
  - 用 **Session 1**：查 task、version 校验、`update_status_to_running_if_pending`、commit；
  - 调用 **`execute_task_impl(task_record)`**（**不再传入 session**）；
  - 用 **Session 2**：`update_status` 写最终状态，commit。
- 子类 `execute_task_impl` 签名从 `(session, task_record)` 改为 **`(task_record)`**；若实现中需要访问 DB，在实现内部用 session 工厂开短 session 自行读写。

### 3.2 行为不变

- 乐观锁语义不变：仍先 pending → running，再执行业务，再 success/failed；
- 失败时仍写 `execution_error_message`，成功写 `execution_result` / `execution_return_key`；
- 队列侧仍是一次 `run_one_batch_task` 处理一条 item，不改变并发模型。

---

## 4. 涉及模块与改动点

### 4.1 队列消费者（`backend/pipeline/batch_task_queue_service.py`）

- **现状**：`async with session_factory() as session:` 后调用 `run_one_batch_task(session, item)`，再 `session.commit()`。
- **改动**：不再传入 `session`，改为传入 **session 工厂**（例如 `get_session_factory()`），调用形如 `run_one_batch_task(session_factory, item)`；**不再**在消费者内对本次执行做 commit（commit 在模版内两段 session 各自完成）。
- 若保留“消费者层一次 with”的写法，可改为 `run_one_batch_task(session_factory, item)` 且 with 块内不 commit，仅用于兼容或后续扩展；推荐是消费者直接调用 `run_one_batch_task(session_factory, item)`，不再为执行过程持有 session。

### 4.2 执行服务（`backend/domain/batch/batch_task_execute_service.py`）

- **现状**：`run_one_batch_task(self, session: AsyncSession, item: BatchTaskQueueItem)`，用 `session` 创建 executor 并调用 `executor.run_one_task(session, item)`。
- **改动**：
  - 方法签名为 `run_one_batch_task(self, session_factory, item)`（或保留兼容的 `session` 重载由内部取工厂，见下）；
  - 内部通过 `session_factory` 在需要时创建 session，**不再**把“调用方传入的一个 session”一路传下去；
  - 创建 executor 时：若 executor 仍需要“能创建 session”的能力，可传入 `session_factory`，而不是传入一个固定 session。具体为：`executor.run_one_task(session_factory, item)`。

### 4.3 执行模版（`backend/domain/batch/batch_template.py`）

- **ExecuteTemplate.run_one_task**  
  - **现状**：`run_one_task(self, session, item)`，全程使用同一个 `session`（查 task、乐观锁更新、`execute_task_impl(session, task_record)`、`update_status`）。
  - **改动**：
    - 签名为 `run_one_task(self, session_factory, item)`（或能获取 session 工厂的等价参数）。
    - 内部逻辑：
      1. `async with session_factory() as session:` → `get_by_id`、version 校验、`update_status_to_running_if_pending` → **commit**，退出 with（Session 1 结束）；
      2. 若未通过校验或更新失败则 return，不执行后续；
      3. `result = await self.execute_task_impl(task_record)`（**不再传 session**）；
      4. `async with session_factory() as session:` → 根据 result/异常调用 `update_status(..., success/failed, ...)` → **commit**，退出 with（Session 2 结束）。
    - `execute_task_impl` 若需访问 DB，在子类内部用 `session_factory()` 开短 session 使用。

- **ExecuteTemplate.execute_task_impl**  
  - **现状**：`async def execute_task_impl(self, session: AsyncSession, task_record: BatchTaskRecord) -> BatchTaskExecutionResult`。
  - **改动**：改为 `async def execute_task_impl(self, task_record: BatchTaskRecord) -> BatchTaskExecutionResult`，去掉 `session` 参数。所有子类实现同步修改：不再使用传入的 session；需要 DB 时在实现内通过依赖注入的 session_factory（或从应用获取的工厂）创建短 session。

### 4.4 执行器子类（如 `PipelineEmbeddingExecutor`）

- **现状**：`execute_task_impl(session, task_record)`，可能用 `session` 做查询或写入。
- **改动**：
  - 实现改为 `execute_task_impl(task_record)`；
  - 若需 DB：在实现内部通过构造函数注入的 `session_factory`（或全局/应用提供的工厂）执行 `async with session_factory() as session:` 做必要读写，用毕即关闭，不长时间持有。

### 4.5 执行器创建方式（BatchTaskExecuteService 与子类）

- 当前：`factory(session)` 返回 executor，executor 内部用传入的 `session` 建 `BatchTaskRepository`。
- 改动后：executor 需要做 DB 操作时，应使用“短 session”；因此建议：
  - 工厂签名为 `ExecutorFactory = Callable[[SessionFactory], ExecuteTemplate]`（或传入可获取 session 的上下文），例如 `factory(session_factory)` 返回 executor；
  - executor 构造函数接收 `session_factory`（及可选的 `task_repo` 若需复用）；在 `run_one_task` 的两段 session 内，用当前段的 `session` 创建 `BatchTaskRepository` 给模版用；`execute_task_impl` 若需 DB，由子类在内部用 `self._session_factory` 开短 session。
- 另一种等价做法：仍传 `session` 但仅用于“当前这一段”的 repo，模版内部两段 session 由模版自己用 `session_factory()` 创建，executor 只持有 `session_factory` 和 `task_repo` 的创建方式（例如每段用当前 session 建 BatchTaskRepository）。两种方式二选一，在实现时统一即可。

---

## 5. 接口契约变更小结

| 位置 | 当前 | 改造后 |
|------|------|--------|
| 消费者 | `run_one_batch_task(session, item)`，外层 commit | `run_one_batch_task(session_factory, item)`，无外层 commit |
| BatchTaskExecuteService.run_one_batch_task | `(session, item)` | `(session_factory, item)` |
| ExecuteTemplate.run_one_task | `(session, item)` | `(session_factory, item)`，内部开两段 session |
| ExecuteTemplate.execute_task_impl | `(session, task_record)` | `(task_record)` |
| ExecutorFactory（若保留工厂） | `(session) -> ExecuteTemplate` | `(session_factory) -> ExecuteTemplate` 或等价 |

---

## 6. 实现顺序建议

1. **ExecuteTemplate**：`execute_task_impl` 改为只收 `task_record`；`run_one_task` 改为接收 `session_factory`，内部实现两段 session 逻辑（含两处 commit）。
2. **所有 execute_task_impl 子类**：去掉 `session` 参数，如需 DB 则内部使用 session_factory（需注入到 executor）。
3. **BatchTaskExecuteService**：`run_one_batch_task` 改为接收 `session_factory`，创建 executor 时传入 `session_factory`，调用 `run_one_task(session_factory, item)`。
4. **batch_task_queue_service**：消费者改为传入 `get_session_factory()`，调用 `run_one_batch_task(session_factory, item)`，去掉对单次执行的长 session 与 commit。
5. 回归：单条任务执行、成功/失败回写、乐观锁与 version 校验行为与现网一致；并发下连接池与事务时长明显缩短（可通过日志或监控观察）。

---

## 7. 风险与注意点

- **子类若强依赖“整条链路一个 session”**：必须改为在 `execute_task_impl` 内按需开短 session，或通过参数注入 session_factory，避免隐式依赖长 session。
- **事务边界**：两段 session 各自 commit，中间没有跨 session 事务；若业务要求“乐观锁更新与结果更新在同一事务”，当前方案不满足（当前设计是“先提交 running，再提交结果”），需在评审时确认可接受。
- **ExecutorFactory 与依赖**：若 executor 需在 `execute_task_impl` 内访问 DB，需在构造时注入 `session_factory`（或等价），并统一约定“实现内按需开短 session”，避免再出现长 session 贯穿业务。

---

## 8. 开发进度

| # | 项目 | 状态 | 说明 |
|---|------|------|------|
| 1 | ExecuteTemplate.run_one_task(session_factory, item) 两段 session | ✅ 已完成 | batch_template.py：Session1 加载/校验/乐观锁并 commit；execute_task_impl(task_record)；Session2 回写状态并 commit |
| 2 | ExecuteTemplate.execute_task_impl(task_record) 无 session | ✅ 已完成 | 抽象方法去掉 session 参数 |
| 3 | PipelineEmbeddingExecutor | ✅ 已完成 | __init__(session_factory)；execute_task_impl(task_record) 内 `async with self._session_factory() as session` 做读写并 commit |
| 4 | BatchTaskExecuteService.run_one_batch_task(session_factory, item) | ✅ 已完成 | batch_task_execute_service.py；ExecutorFactory(session_factory) → executor；run_one_task(session_factory, item) |
| 5 | 消费者传 session_factory、无长 session | ✅ 已完成 | batch_task_queue_service._consumer_loop 直接 `await run_one_batch_task(session_factory, item)`，不再持 session、不再外层 commit |

**文档编号**：030203；批次任务执行流程 Session 拆分，避免长时间业务占用同一 DB 连接与事务。
