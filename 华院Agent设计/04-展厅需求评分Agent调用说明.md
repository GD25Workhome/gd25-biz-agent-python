# 展厅需求评分 Agent 调用说明

> **状态**：V1 可联调（能力勉强可用，需人工核验门控）  
> **服务**：`gd25-biz-agent-python`  
> **接口**：`POST /api/v1/huayuan/radar-event-score`  
> **设计依据**：`03-二阶段的Agent任务.md`；产品规则二见 `产品提供-260903/数字文旅商机中心可配置规则设计v2.md` §3

本文供 **exhibition / 其它业务服务** 对接使用。字段均为 **snake_case**。

---

## 1. 接口做什么 / 不做什么


| 本服务做                          | 本服务不做                               |
| ----------------------------- | ----------------------------------- |
| 按企业基础信息联网检索公开证据（AnySearch）    | 不定最终 **S1–S4**（由调用方按分数阈值 + §3.2 封顶） |
| 输出两维离散分 + 证据 URL / 摘录         | 不灌巨潮全文；不做日频调度                       |
| 过滤明显噪声（展会展位、线上软件「体验中心」等，尽力而为） | 不保证证据权威；开放搜索默认按 **P2 / 待核验** 处理     |
| 无 Session，固定绑定本流程             | 不替代人工核验与发布门控                        |


**端到端建议：**

```text
调用方组装 company → POST /huayuan/radar-event-score
  → 解析 radar_event_score（分 + 证据 + admission_hint）
  → 调用方：准入/失效闸门 → 分数映射 S → 落库 → 人工核验
```

---

## 2. 调用约定


| 项             | 值                                                             |
| ------------- | ------------------------------------------------------------- |
| Method / Path | `POST /api/v1/huayuan/radar-event-score`                      |
| Content-Type  | `application/json`                                            |
| 鉴权            | V1 无业务登录；依赖内网/网关                                              |
| 建议超时          | 服务端墙钟 **120s**；客户端建议 **≥ 130s**                             |
| 成功            | HTTP **200** + 强类型 `radar_event_score`                        |
| 执行超时          | HTTP **504**（超过 120s 取消本次 Agent 运行）                          |
| 业务/解析失败       | HTTP **500**（含模型 JSON 非法、非法分值、有分无 URL 等）；调用方可记 job FAILED 并重试 |
| 参数校验失败        | HTTP **422**（如 `query` 空、`company_name` 空）                    |


本地示例：

```bash
curl -s http://127.0.0.1:8000/api/v1/huayuan/radar-event-score \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "请评估该公司实体展厅/长期展示接待空间的新建翻新升级需求证据强度",
    "context": {
      "company": {
        "company_name": "鼎捷数智",
        "stock_code": "300378",
        "aliases": ["鼎捷软件"]
      },
      "event_job_id": 1001,
      "time_from": "2025-01-01",
      "time_to": "2026-09-09"
    }
  }'
```

---

## 3. 请求体

### 3.1 顶层


| 字段         | 类型     | 必填  | 说明                             |
| ---------- | ------ | --- | ------------------------------ |
| `query`    | string | 是   | 任务提示；不可空白。可固定写死展厅需求评估口径        |
| `context`  | object | 是   | 见下                             |
| `trace_id` | string | 否   | 建议传 32 位 hex，便于双边日志串联；不传则服务端生成 |


### 3.2 `context`


| 字段                       | 类型     | 必填  | 说明                                  |
| ------------------------ | ------ | --- | ----------------------------------- |
| `company`                | object | 是   | 企业基础信息                              |
| `time_from` / `time_to`  | string | 否   | 关注时间窗（提示用，搜索引擎不保证严格过滤）              |
| `event_job_id`           | int    | 建议  | 调用方任务 ID，仅日志透传                      |
| `query_hint`             | string | 否   | **可不传**。V1 提示词已固定展厅意图；传入可覆盖默认检索提示文案 |
| `max_search_times`       | int    | 否   | 联网搜索上限，当前测试默认 **20**（工具硬限制；稳定后可改回 3） |
| `max_extract_times`      | int    | 否   | 页面抽取上限，当前测试默认 **8**（工具硬限制；稳定后可改回 2） |
| `max_results_per_search` | int    | 否   | 每次搜索条数，默认 **5**（上限 10）              |


### 3.3 `context.company`


| 字段                    | 类型         | 必填   | 说明                |
| --------------------- | ---------- | ---- | ----------------- |
| `company_name`        | string     | 是    | 标准名，检索与主体校验主依据    |
| `stock_code`          | string     | 强烈建议 | 如 `300378`，提高主体匹配 |
| `company_id`          | int/string | 建议   | 业务侧企业 ID          |
| `aliases`             | string[]   | 否    | 别名，参与主体匹配         |
| `industry` / `region` | string     | 否    | 辅助消歧              |


**最小可用请求：** `query` + `context.company.company_name`。  
**推荐：** 再带 `stock_code`、`aliases`、`event_job_id`、`trace_id`、时间窗。

---

## 4. 响应体

### 4.1 顶层


| 字段                  | 类型     | 说明                    |
| ------------------- | ------ | --------------------- |
| `trace_id`          | string | 本次追踪 ID               |
| `radar_event_score` | object | 评分结果（见下）              |
| `response`          | string | 可选；结果 JSON 字符串，便于人工查看 |


### 4.2 `radar_event_score` 核心字段


| 字段                                                | 类型       | 说明                                                                          |
| ------------------------------------------------- | -------- | --------------------------------------------------------------------------- |
| `exhibition_related`                              | bool     | 是否与实体展厅/长期展示接待空间相关                                                          |
| `subject_confidence`                              | string   | `high` | `medium` | `low` | `unknown`                                       |
| `space_object` / `action` / `place` / `time_text` | string?  | 事实字段                                                                        |
| `evidence_score`                                  | int?     | **仅** `85/75/60/45/25/10`；不准入/失效为 `null`                                    |
| `specificity_score`                               | int?     | **仅** `15/10/5/0`；不准入/失效可为 `null`                                           |
| `total_score`                                     | int?     | 服务端按两维之和重算；不准入/失效为 `null`                                                   |
| `tags`                                            | string[] | 事件标签，不计分                                                                    |
| `expired_or_done`                                 | bool     | 是否已失效/结束                                                                    |
| `fact_status`                                     | string   | `confirmed` | `inferred` | `unknown` | `conflict`                           |
| `admission_hint`                                  | string   | `pass` | `reject_unrelated` | `pending_verify` | `expired`（**提示**，最终闸门在调用方） |
| `score_reason`                                    | string?  | 打分/拒绝理由                                                                     |
| `evidences`                                       | array    | 纳入计分的证据（有分必有可访问 URL）                                                        |
| `discarded`                                       | array    | 被排除的命中及原因                                                                   |
| `search_count` / `extract_count`                  | int      | 本次实际工具调用次数（可观测）                                                             |


### 4.3 `evidences[]` 单条


| 字段                            | 说明                                                                                              |
| ----------------------------- | ----------------------------------------------------------------------------------------------- |
| `title` / `summary` / `quote` | 标题、摘要、短摘（建议 ≤200 字）                                                                             |
| `url`                         | 原文链接（计分证据必须为 http(s)）                                                                           |
| `publish_date`                | 原文日期表述（可能为空）                                                                                    |
| `source_host`                 | 主机名                                                                                             |
| `authority_tier`              | 启发式：`regulator_or_exchange` / `gov` / `company_official` / `media` / `ugc_or_noise` / `unknown` |
| `kept`                        | 是否纳入计分                                                                                          |


> `authority_tier` **不是**产品 P0/P2 权威定论。V1 全部 AnySearch 证据建议调用方仍按 **P2、默认待核验** 落库。

### 4.4 成功响应示例（结构示意）

```json
{
  "trace_id": "f0d48c988dcb745651e6d3c94acd4156",
  "radar_event_score": {
    "exhibition_related": true,
    "subject_confidence": "high",
    "space_object": "展示接待中心",
    "action": "新建",
    "place": "湖州",
    "time_text": "2025-07",
    "evidence_score": 75,
    "specificity_score": 10,
    "total_score": 85,
    "tags": ["新建"],
    "expired_or_done": false,
    "fact_status": "inferred",
    "admission_hint": "pass",
    "score_reason": "...",
    "evidences": [
      {
        "title": "...",
        "summary": "...",
        "quote": "...",
        "url": "https://...",
        "publish_date": null,
        "source_host": "example.com",
        "authority_tier": "unknown",
        "kept": true
      }
    ],
    "discarded": [],
    "search_count": 2,
    "extract_count": 1
  },
  "response": "{...}"
}
```

---

## 5. 调用方如何用结果（定级权威在你侧）

建议处理顺序（与业务规则二对齐）：

```text
1. exhibition_related=false 或 admission_hint=reject_unrelated → 不准入，不写 S
2. subject_confidence=unknown 或关键事实不明 → 待核验，不直接当弱 S
3. expired_or_done=true → 已失效，不算总分
4. 校验 evidence_score / specificity_score 是否在合法枚举；total 可自行重算 = 两维之和
5. 按产品分数区间映射候选 S1–S4，再套用 §3.2 封顶
6. 证据来源均为开放搜索 → 强制待核验；S1/S2 不得自动发布
```

分数区间（产品 §3.5，供参考）：


| 候选等级 | 分数     |
| ---- | ------ |
| S1   | 75–100 |
| S2   | 50–74  |
| S3   | 25–49  |
| S4   | 0–24   |


**禁止**把 Agent 可能附带的调试等级字段当权威（当前契约也不输出最终 S）。

---

## 6. 错误与重试


| 情况                           | HTTP | 建议                             |
| ---------------------------- | ---- | ------------------------------ |
| `query` / `company_name` 为空  | 422  | 修正入参                           |
| 模型输出非法 JSON / 非法分值 / 有分无 URL | 500  | 按 `trace_id` 查日志；可重试同 job      |
| 流程/工具异常                      | 500  | 重试；注意 AnySearch 限流与超时          |
| 长时间无响应                       | —    | 服务端 **120s** 墙钟超时 → **504**；客户端超时建议略大于 120s |
| 执行超时                         | 504  | 降低 `max_search_times` 后重试；查 `trace_id` 日志     |


幂等：本接口**无业务幂等键**；调用方应用 `event_job_id` / `trace_id` 自行防重。

---

## 7. V1 已知限制（对接预期）

1. **证据通道仅 AnySearch**：覆盖与权威性有限，须人工核验。
2. **可能混项目 / 分数偏高**：提示词已约束「单事件、宁低勿高」，仍建议调用方按证据 URL 复核。
3. **线上「体验中心」易误触**：已提示排除；仍可能偶发，需看 `discarded` 与 `score_reason`。
4. **页面抽取可能失败**（如 422）：失败时模型可能仅凭摘要推断，`fact_status` 宜按 `inferred` 对待。
5. **时间窗非强制过滤**：`time_from`/`time_to` 只影响提示，不保证结果落在窗内。
6. **搜索/抽取次数**：当前测试默认 **20 / 8**，由工具**硬限制**，请求可覆盖；稳定后建议改回更低默认。

---

## 8. 联调检查清单

- [ ] 能通：最小请求返回 200，且含 `radar_event_score`  
- [ ] 必填校验：空 `query` / 空 `company_name` → 422  
- [ ] 非法分值或无 URL 有分 → 500，job 可重试  
- [ ] `evidences[].url` 可落库并前端跳转  
- [ ] `admission_hint` / `exhibition_related` 驱动本系统闸门，而非直接信任自动发布  
- [ ] 日志可用 `trace_id` / `event_job_id` 双边对齐  

---

## 9. 相关代码位置（本仓库）


| 路径                                               | 说明           |
| ------------------------------------------------ | ------------ |
| `backend/app/api/routes/huayuan_radar_event.py`  | 路由           |
| `backend/app/api/schemas/huayuan_radar_event.py` | 请求/响应 Schema |
| `config/flows/huayuan_radar_event_agent/`        | 流程与提示词       |
| `backend/domain/tools/anysearch_tool.py`         | AnySearch 工具 |
| `cursor_test/test_huayuan_radar_event.py`        | 单测           |


OpenAPI：服务启动后访问 `/docs`，查找 `POST /api/v1/huayuan/radar-event-score`。