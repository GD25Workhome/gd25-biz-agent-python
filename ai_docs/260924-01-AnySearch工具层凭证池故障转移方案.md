---
date: 260924
---

# AnySearch 工具层：凭证池故障转移

**文档编号**：260924-01
**类型**：改造方案
**对象**：`backend/domain/tools/anysearch_tool.py`（`anysearch_web_search` / `anysearch_extract`）
**结论一句话**：在工具内部维护多把 key 的进程内凭证池；一次调用先判定响应是否成功，仅在 401 / 402 / 403 时换下一把并熔断已废 key。选 key 不进入 LangGraph。

---

## 0. 和节点层方案的边界

| 层 | 文档 | 负责 |
|---|---|---|
| 工具层 | 本文 | 同一请求内换 key；熔断单把 key；向调用方返回稳定 `error_code` |
| 节点层 | `260924-02-采集节点AnySearch熔断后降级方案.md` | 池里没有存活 key 时，采集节点不再扇出 AnySearch，博查与知识库继续 |

`query_planner` 与 `evidence_gather` 都调用这两个工具。它们共用同一进程内的池：规划阶段把某把 key 打成 402 后，采集阶段直接跳过这把 key。

---

## 1. 现状

`_resolve_api_key()` 按顺序读 `ANY_SEARCH_API_KEY`、`ANYSEARCH_API_KEY`，**取第一把非空值**。两个名字是别名，不是主备。

搜索与抽取都走 `_auth_headers()` → `POST https://api.anysearch.com/v1/...`。非 2xx 时 `raise_for_status()`，工具返回 `ok: false` 和异常字符串。调用方看不到 HTTP 状态，也分不清额度用完、限流、参数错误。

AnySearch 没有剩余用量接口。额度用完只能在当次响应里看到：**402 = 额度耗尽**。成功响应是 HTTP 2xx 且业务体 `code == 0`。文档见 [POST /v1/search](https://anysearch.com/docs/api-endpoints/v1-search)、[POST /v1/extract](https://anysearch.com/docs/api-endpoints/v1-extract)。

本地配额 `mark_anysearch` / `mark_extracted` 在发 HTTP **之前**占位。换 key 重试必须仍算一次搜索或一次抽取。

---

## 2. 目标

大量调用把当前 key 打满（402）或 key 无效（401 / 403）时，**同一次工具调用**用下一把存活 key 重放同一请求体。最终成功时，Agent 与采集节点看到的仍是现在的成功 JSON。

单 key 部署保持现有行为：这把 key 被拒后直接失败，不匿名重试。

---

## 3. 配置

新增环境变量，逗号分隔，去空白、去重、保持顺序：

```text
ANY_SEARCH_API_KEYS=key_a,key_b,key_c
```

解析顺序：

1. `ANY_SEARCH_API_KEYS` 非空 → 只用这个列表。
2. 该变量为空 → 将 `ANY_SEARCH_API_KEY`、`ANYSEARCH_API_KEY` 中的非空值按此顺序并入池（去重）。现网只配一把时，池大小为 1。

key 本身不得包含逗号。配置进 `backend/app/config.py` 的 Settings，与现有两个单 key 字段并存。

同步改说明，不写真实 key：

- `.env.example`
- `huaYuanTestDeploy/环境变量所有字段说明.md`
- `deploy/k8s/huayuan-agent.yaml` 用占位符

---

## 4. 怎样算「这次调用正常」

只看 HTTP 状态和业务 `code`。空结果列表是正常的「没搜到」。

| 结果 | 判定 | 动作 |
|---|---|---|
| HTTP 2xx，且 `code` 缺失或 `code == 0` | 成功 | 返回正文，结束 |
| HTTP 2xx，`code` 存在且不为 0 | 业务失败 | 不换 key，返回 `anysearch_upstream_error` |
| 401、402、403 | 这把 key 不可用 | 熔断该 key，换下一把重放 |
| 400、415、422 | 请求本身有问题 | 不换 key，返回 `anysearch_bad_request` |
| 429 | 限流（key、用户或 IP 都可能） | 不换 key，不熔断，返回 `anysearch_rate_limited` |
| 502 及其它 5xx | 上游故障 | 不换 key，返回 `anysearch_upstream_error` |
| 超时 | 网络 | 不换 key，返回 `anysearch_timeout` |
| 2xx 且 `results` 为空 | 成功 | 不换 key |

429 不换 key：官方说明限流主体可能是用户或来源 IP，同账号换 key 仍会 429，换下去会把池打穿。

402 的响应体在匿名超额时可能带自动生成的 `username` / `password` / `api_key`。实现只从响应里取 `request_id`（或响应头 `X-Request-ID`）。日志禁止打印响应体、`Authorization` 和完整 key。排障用池内序号加 key 末 4 位。

全部存活 key 都返回 401 / 402 / 403 之后，返回 `anysearch_keys_exhausted`。**不再发不带 Authorization 的匿名请求。**

---

## 5. 进程内凭证池

放在 `anysearch_tool.py`（或同目录仅被该工具使用的小模块）。搜索与抽取共用一个实例。

状态：

- 有序 key 列表（启动时从 Settings 解析一次）
- 已熔断 key 的集合
- `asyncio.Lock`

方法：

- `live_keys() -> list[str]`：按配置顺序返回尚未熔断的 key
- `mark_exhausted(key) -> None`
- `has_live_key() -> bool`：给采集节点做扇出前判断（见 260924-02）

多副本各持一份内存。每个副本对已废 key 最多再打出一批在途 402，然后记入熔断集。不上 Redis。

进程重启后熔断集清空，下一请求会再探测。402 若是日额度，重启多试一次可以接受。本次不做半开探测、不做跨日 TTL。

并发：在锁内挑选下一把未熔断 key 并在 401 / 402 / 403 时标记。已经发出的请求仍可能同时 402，然后一起落到下一把。这是可接受的。

---

## 6. 调用流程

搜索、抽取的 HTTP 收成一个内部函数，例如 `_post_with_key_failover(path, payload) -> 成功 body 或失败结构`。配额占位、query 去重、结果 enrichment 留在现有工具函数里，顺序不变：

1. 上下文与 `can_anysearch` / `can_extract` 校验。
2. `mark_anysearch` / `mark_extracted` 占位一次。
3. 进入 failover：
   - 没有存活 key：直接 `anysearch_keys_exhausted`，不发 HTTP。
   - 对当前存活列表逐把 POST 同一 payload。
   - 成功即返回。
   - 401 / 402 / 403：熔断并试下一把。
   - 其它失败：立刻返回，不再试后续 key。
4. 成功 body 仍走现有 `_normalize_search_items` / 抽取正文解析。

失败 JSON 契约（节点层只认 `error_code`，不解析中文 `error`）：

```json
{
  "ok": false,
  "error": "AnySearch 凭证不可用",
  "error_code": "anysearch_keys_exhausted",
  "http_status": 402
}
```

`error_code` 取值：

| error_code | 何时 |
|---|---|
| `anysearch_keys_exhausted` | 无存活 key，或存活 key 全部 401 / 402 / 403 |
| `anysearch_bad_request` | 400 / 415 / 422 |
| `anysearch_rate_limited` | 429 |
| `anysearch_upstream_error` | 5xx，或 2xx 但 `code != 0` |
| `anysearch_timeout` | 超时 |

成功 JSON 字段保持现状。不把 `key_index` 写进工具 Observation，避免进模型上下文。

---

## 7. 改动文件

| 文件 | 改动 |
|---|---|
| `backend/domain/tools/anysearch_tool.py` | 凭证池、响应分类、failover |
| `backend/app/config.py` | `ANY_SEARCH_API_KEYS` |
| `.env.example` | 字段说明 |
| `huaYuanTestDeploy/环境变量所有字段说明.md` | 字段说明 |
| `deploy/k8s/huayuan-agent.yaml` | 占位环境变量 |
| `cursor_test/test_anysearch_key_failover.py` | 见第 8 节 |

不改 `flow.yaml`，不改博查工具，不改 LangGraph 边。

---

## 8. 测试

`cursor_test/test_anysearch_key_failover.py`，HTTP 用 mock，不打真实 AnySearch。

- 第一把 402、第二把 200 且 `code == 0` → 成功，且第二次请求带第二把 key。
- 401、403 同样换 key。
- 两把都 402 → `anysearch_keys_exhausted`，且没有不带 Authorization 的请求。
- 429 → 只打第一把，且该 key 仍存活。
- 200 且 `results: []` → 成功，不打第二把。
- 502、超时 → 不打第二把。
- 未配 `ANY_SEARCH_API_KEYS`、只配 `ANY_SEARCH_API_KEY` → 池大小为 1，行为与现在一致。
- 日志 fixture 中不出现完整 key，也不出现 402 体里的 `password` / `api_key`。

---

## 9. 风险

- 同账号的多把 key 解决不了 429。限流仍按第 4 节原样返回。
- 在途并发会在熔断前多打几次 402。池按配置顺序消耗，不会无界重试。
- 402 体可能含对方新发的密钥。实现禁止把该体写入日志、trace 或配置。
