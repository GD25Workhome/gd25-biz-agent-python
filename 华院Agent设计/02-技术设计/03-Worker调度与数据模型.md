# 03 · Worker 调度与数据模型

> 上游：[00-当前技术设计-总览.md](../00-当前技术设计-总览.md)  
> 本文只讲 event worker 的认领、执行、重试与数据模型；评分/落库细节见 `02`，HTTP 见 `01`。

---

## 1. 两种启动方式

| 方式 | 入口 | 说明 |
|---|---|---|
| 独立进程 | `python -m radar_score` | 只跑 worker，不开 HTTP |
| API 进程内 | `RADAR_SCORE_WORKER_IN_APP=true` | FastAPI lifespan 启动后台线程；与 HTTP 共进程 |

默认 `RADAR_SCORE_WORKER_IN_APP=false`；K8s 测试环境当前设为 `true`。

```text
radar_score/__main__.py     -> load_score_settings() -> ScoreScheduler.run_forever()
radar_score/in_app.py       -> start_radar_score_in_app() / stop_radar_score_in_app()
radar_score/scheduler.py    -> _tick / _fill / _run_one
radar_score/repository.py   -> claim / reclaim / release
radar_score/execute.py      -> run_event_end_to_end
radar_score/prepare.py      -> fetch job/company/history -> request body
```

---

## 2. 调度循环 `scheduler.py`

```text
while not stop:
  _tick()
    -> reclaim_stale()          # 先回收超时 RUNNING
    -> _event_claim_allowed()   # 未配 DEEPSEEK_SEARCH_KEY 则暂停
    -> _fill()                  # 按空闲槽位认领
  _wait(poll_interval_sec 或 2s)
```

| 配置 | 默认 | 说明 |
|---|---:|---|
| `RADAR_SCORE_EVENT_CONCURRENCY` | 2 | 同时在跑的 event 任务上限 |
| `RADAR_SCORE_POLL_INTERVAL_SEC` | 15 | 无任务时轮询间隔；有在途任务时最多 2s |
| `RADAR_SCORE_STALE_TIMEOUT_SEC` | 2400 | RUNNING 超时回收 |
| `RADAR_SCORE_SHUTDOWN_WAIT_SEC` | 30 | 停止时等待在途任务 |
| `RADAR_SCORE_MAX_RETRY` | 3 | 可重试错误的最大重试次数 |
| `RADAR_TENANT_ID` | 空 | 可选：只认领指定租户 |

### 2.1 DeepSeek key 门禁

`_event_claim_allowed()`：

```text
resolve_deepseek_key()  # DEEPSEEK_SEARCH_KEY，回退 DEEPSEEK_API_KEY
  None -> 暂停认领，任务留 PENDING；只在停领/恢复交界各打一条日志
  非空 -> 恢复认领
```

### 2.2 停止

`run_forever` 收到 stop 后等待在途任务最多 `shutdown_wait_sec`；仍未结束的任务保持 RUNNING，由下一轮 `reclaim_stale` 回收。

---

## 3. 认领 / 回收 / 重试 `repository.py`

### 3.1 状态

| 值 | 含义 |
|---:|---|
| 0 | PENDING |
| 1 | RUNNING |
| 2 | SUCCESS |
| 3 | FAILED |

只操作 `radar_event_job`。

### 3.2 认领 `claim_jobs`

```sql
SELECT id FROM radar_event_job
WHERE deleted=b'0' AND status=0 [AND tenant_id=%s]
ORDER BY id ASC LIMIT %s
FOR UPDATE SKIP LOCKED;

UPDATE radar_event_job
SET status=1, locked_by=%s, locked_at=%s, updater=%s, update_time=%s
WHERE id=%s AND status=0 AND deleted=b'0';
```

- 只有 `rowcount=1` 才算领到；
- 锁标识 `python-score-{host}:{pid}`，≤64；
- commit 后返回已认领 id。

### 3.3 超时回收 `reclaim_stale`

```sql
UPDATE radar_event_job
SET status=0, locked_by=NULL, locked_at=NULL,
    error_message='RUNNING 超时，退回待执行',
    updater=%s, update_time=%s
WHERE status=1 AND locked_at IS NOT NULL AND locked_at < now-INTERVAL stale_timeout
  AND deleted=b'0' [AND tenant_id=%s];
```

`java-manual` 与 `python-score-` 都回收，避免任一侧崩溃后任务永久卡住。

### 3.4 失败处置 `release_claim`

```text
SELECT retry_count ... WHERE id=%s AND status=1 AND locked_by=%s
status = next_status(retryable, retry_count, max_retry)
UPDATE ... retry_count=retry_count+1, locked_by=NULL, locked_at=NULL,
           error_message=%s, status=status
```

`next_status`：

```text
retryable && retry_count + 1 <= max_retry -> PENDING
否则 -> FAILED
```

### 3.5 可重试判断 `is_retryable`

不可重试（确定性错误）：

```text
pymysql.err.DataError / IntegrityError / ProgrammingError / NotSupportedError
ValueError / TypeError / KeyError
```

会**沿异常链**（`__cause__` / `__context__`，有界 8 层）判断；路由把 `ValueError` 包成 `HTTPException` 时仍能识别内层确定性错误。

---

## 4. 单任务执行 `execute.py`

```text
run_event_end_to_end(settings, job_id)
  conn = connect(settings)
  job, company = prepare.fetch_job_and_company(conn, job_id)
  history = prepare.load_history_events(conn, company_id)
  body = prepare.build_request_body(job, company, history)
  resp = await _score(body)                 # 进程内调 route
  scores = RadarEventScoreResult[]          # radar_event_scores / radar_event_score
  for score in scores:
    outcome = self_check.check(score)
    if not outcome.ok: 跳过该事件（SELF_CHECK_FAILED）
    decision = event_update.decide_action(score, history)
    region = region_resolve.resolve_event_region(conn, place, company, place_region_id)
    if INSERT:
      event_id = radar_event_store.insert_event(...)
      replace_evidences(...)
      touch_latest_event(...)
    else:
      event_id = decision.event_id            # NOOP
  if passed == 0: update_job_failed(...)
  else: update_job_success(event_id=written_event_id, stats, revision, cost_ms)
  commit
```

异常：

```text
rollback
  -> is_retryable(ex) ? release_claim(retryable=True) -> PENDING
                      : release_claim(retryable=False) -> FAILED
  -> raise（由 scheduler 记录日志）
```

单任务一事务：事件 / 证据 / 企业指针 / 任务状态全成功或全回滚。

---

## 5. 请求组装 `prepare.py`

### 5.1 读取任务 / 企业

```sql
SELECT * FROM radar_event_job WHERE id=%s AND deleted=b'0' [AND tenant_id=%s];
SELECT * FROM radar_company  WHERE id=%s AND deleted=b'0';
```

### 5.2 历史事件

`load_history_events`：

- 扫描上限 200 行；
- 按商机族聚组：`root_key = parent_event_id or id`，每组只给最新一条代表行；
- 族内状态取「或」：`published` / `closed` 任一为真则代表行为真；
- 补 `radar_opportunity.status / close_reason`；
- 输出字段：`id`、`event_name`、`root_event_id`、`space_object`、`place`、`procurement_scope`、`event_stage`、`exhibition_stage`、`system_level`、`verify_status`、`validity_status`、`expired_or_done`、`published`、`total_score`、`signal_summary`、`rule_version`、`update_time`、`opportunity_status`。

### 5.3 请求体

```json
{
  "query": "评估「{company_name}」的展厅需求证据强度并给出评分与证据。",
  "trace_id": "<uuid>",
  "context": {
    "company": { "...": "企业字段" },
    "time_from": "...",
    "time_to": "...",
    "query_hint": "...",
    "event_job_id": 123,
    "history_events_json": "[...]"
  }
}
```

与 Java 手动路径的请求体形状一致；不再调用 Java prepare/complete。

---

## 6. 数据模型

### 6.1 `radar_event_job`

| 列 | 用途 |
|---|---|
| `id` / `company_id` / `tenant_id` | 任务 / 企业 / 租户 |
| `status` | 0 PENDING / 1 RUNNING / 2 SUCCESS / 3 FAILED |
| `locked_by` / `locked_at` | 认领锁 |
| `retry_count` / `error_message` | 重试与失败原因 |
| `time_from` / `time_to` | 采集侧时间窗（提示） |
| `knowledge_json` | 历史字段；当前规则二 v3 不使用知识库召回 |
| `event_id` | 成功事件 id（NOOP 可为空） |
| `agent_trace_id` | 评分 trace |
| `acp_raw_json` | 模型原始响应 |
| `stats_json` | 事件统计 / 决策 |
| `revision_json` | rule_gate / auditor 留痕 |
| `cost_ms` | 耗时 |
| `deleted` / `creator` / `updater` / `create_time` / `update_time` | 审计 |

### 6.2 `radar_event` / `radar_event_evidence`

见 [02-评分、自检与落库规则.md](02-评分、自检与落库规则.md) §5。

### 6.3 关联表

| 表 | 用途 |
|---|---|
| `radar_company` | 企业；`latest_event_id` 指向当前代表事件（只前移） |
| `radar_opportunity` | 商机；`status` 参与已关闭 / 已签署判断 |
| `region` / `region_alias` | 行政区划字典；区域解析只读 |

---

## 7. 状态流

```text
PENDING(0)
   | claim_jobs (FOR UPDATE SKIP LOCKED)
   v
RUNNING(1)
   | success
   v
SUCCESS(2)

RUNNING(1)
   | reclaim_stale (locked_at 超时)
   v
PENDING(0)

RUNNING(1)
   | 确定性错误 / 超过 max_retry
   v
FAILED(3)

RUNNING(1)
   | 可重试错误且未超 max_retry
   v
PENDING(0)
```

---

## 8. 代码锚点

```text
radar_score/__main__.py
radar_score/in_app.py
radar_score/scheduler.py
radar_score/repository.py
radar_score/execute.py
radar_score/prepare.py
radar_score/config.py
backend/app/config.py
backend/main.py
```
