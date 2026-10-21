# 01 · HTTP 契约与 Agent 流程

> 上游：[00-当前技术设计-总览.md](../00-当前技术设计-总览.md)  
> 本文只讲 HTTP 入口、flow v3、提示词、工具与 provider；评分/落库见 `02`，调度见 `03`。

---

## 1. 路由与执行入口

| 项 | 值 |
|---|---|
| Method / Path | `POST /api/v1/huayuan/radar-event-score` |
| 路由文件 | `backend/app/api/routes/huayuan_radar_event.py` |
| Flow key | `huayuan_radar_event_agent_v3` |
| 会话 | 无 Session；每次请求独立 `trace_id` |
| 鉴权 | 路由本身无业务登录，依赖内网 / 网关 |
| 超时 | 路由本身不设 504；由 Java `radar-event-score-timeout-ms` / 网关控制 |

执行步骤：

```text
1. 生成 / 读取 trace_id
2. 构造 prompt_vars（公司、时间窗、历史事件、validity_floor）
3. FlowManager.get_flow("huayuan_radar_event_agent_v3")
4. graph.ainvoke(initial_state, config)
5. resolve_scores_from_flow_result（edges_var 优先，回退 AI 文本）
6. 回填 search_count / extract_count
7. 返回 primary + 多事件数组 + revision
```

---

## 2. 请求 Schema

文件：`backend/app/api/schemas/huayuan_radar_event.py`

```json
{
  "query": "请评估该公司展厅项目需求证据强度并给出评分与证据。",
  "trace_id": "可选；不传则由服务端生成",
  "context": {
    "company": {
      "company_id": 12,
      "company_name": "企业标准名（必填）",
      "stock_code": "300378",
      "aliases": ["别名1", "别名2"],
      "industry": "可选",
      "region": "可选"
    },
    "time_from": "2025-01-01",
    "time_to": "2026-09-09",
    "query_hint": "可选；覆盖默认检索意图",
    "event_job_id": 1001,
    "history_events_json": "可选；worker 自动组装",
    "max_search_times": 10,
    "max_bocha": 10,
    "max_anysearch": 10,
    "max_extract_times": 8,
    "max_results_per_search": 5,
    "knowledge": {
      "enabled": false,
      "max_docs": 20,
      "max_load_times": 3
    }
  }
}
```

说明：

- `company.company_name` 必填且不能为空；`query` 必填。
- `history_events_json` 是字符串（JSON 数组），worker 自动组装；HTTP 调用方通常不传。
- `max_*` / `knowledge` 字段为**请求兼容字段**；v3 的工具链只使用 DeepSeek + region，不再按这些配额召回知识库。
- `trace_id` 不传时由 `secrets.token_hex(16)` 生成。

---

## 3. 响应 Schema

```json
{
  "trace_id": "32 位 hex",
  "radar_event_score": { "...": "第一个事件，兼容旧调用方" },
  "radar_event_scores": [ { "...": "每个达标事件一条" } ],
  "response": "完整 JSON 字符串（radar_event_scores）",
  "revision": { "...": "rule_gate / auditor 留痕，可选" }
}
```

`RadarEventScoreResult` 字段分组：

| 分组 | 字段 |
|---|---|
| 事件身份 | `event_ref`、`event_name`、`event_relation`、`matched_event_id`、`parent_event_id` |
| 展厅对象 | `exhibition_related`、`subject_confidence`、`space_object`、`action`、`place`、`place_region_id` |
| 时间 / 事实 | `time_text`、`signal_time`、`signal_time_evidence_no`、`fact_time_earliest`、`fact_time_earliest_evidence_no`、`fact_status`、`date_precision` |
| 两维分 | `evidence_score`、`specificity_score`、`total_score`、`suggested_level`、`suggested_level_reason` |
| 准入 / 等级 | `admission_hint`、`expired_or_done`、`is_potential`、`signal_category`、`verify_priority_*` |
| 证据 | `evidences[]`（`evidence_no` / `source_type` / `doc_id` / `title` / `summary` / `quote` / `url` / `publish_date` / `source_host` / `authority_tier` / `kept` / `cite_reason`） |
| 丢弃 | `discarded[]`（`title` / `url` / `reason`） |
| v3 扩展 | `target_scope`、`procurement_scope`、`event_stage`、`exhibition_stage`、`planned_time`、`expected_time`、`actual_time`、`tags`、`rule_version` |
| 运行统计 | `search_count`、`extract_count`、`web_hit_count`、`kb_hit_count` |

`search_count` / `extract_count` 若模型漏写，路由会用运行时真实计数回填。

---

## 4. 错误与异常

| 场景 | HTTP | 处理 |
|---|---|---|
| 请求体缺 `query` / `company_name` 为空 | **422** | Pydantic / FastAPI 校验 |
| 流程执行异常、模型输出无法解析、非法分值 | **500** | `HTTPException(500, detail=...)` |
| 流程返回空 `radar_event_score(s)` | **500** | `ValueError` → 500 |
| 客户端 / 网关超时 | 由调用方决定 | 路由不主动返回 504 |

> 生产调用方（Java）应把 4xx 视为不可重试、5xx 视为可重试；worker 侧另有自己的重试分类。

---

## 5. Flow v3

文件：

```text
config/flows/huayuan_radar_event_agent_v3/flow.yaml
config/flows/huayuan_radar_event_agent_v3/prompts/radar_event_v3.md
config/flows/huayuan_radar_event_agent_v3/prompts/radar_event_audit_v3.md
```

节点：

| 节点 | 类型 | 作用 |
|---|---|---|
| `radar_event_react_node` | agent | 单 Agent ReAct：DeepSeek 检索 + 区域字典 + 输出多事件评分 |
| `radar_rule_gate` | function | 确定性硬闸：R9 日期/来源、R7 时效；产出 `radar_audit_required` |
| `radar_event_audit_node` | agent | 语义复核：只降不升；依据给定证据复核时效/准入/等级 |

边：

```text
radar_event_react_node --always--> radar_rule_gate
radar_rule_gate --radar_audit_required == true--> radar_event_audit_node
radar_event_audit_node --always--> END
```

工具：

| 工具 | 作用 |
|---|---|
| `deepseek_web_search(query, count=10, need_content=False)` | 中文联网搜索；摘要命中公告/招标/立项时可取正文 |
| `deepseek_fetch(url)` | 抓取页面正文（Markdown）；不支持 PDF/二进制 |
| `region_lookup(keyword, parent="", limit=10)` | 查行政区划字典，返回 id / name / level / parent_id / path_ids / is_domestic |
| `region_children(region, limit=50)` | 列下级区域，逐级下钻（市 → 区/县） |

模型：

```yaml
provider: huayuan
temperature: 0.2  # react
temperature: 0.1  # auditor
timeout: 300
thinking:
  type: disabled
```

Provider 配置：`config/model_providers.yaml` 只有 `huayuan`，base URL 指向公司 OpenAI 兼容网关，默认模型 `deepseek/deepseek-v4.1-flash`。

---

## 6. Prompt 变量

`build_radar_event_initial_state` 写入 `prompt_vars`：

| 变量 | 来源 | 说明 |
|---|---|---|
| `current_date` | 服务端当前时间 | 模型参考 |
| `validity_floor` | 评估日 − 12 个月 | 时效闸门下界（规则，不是检索提示） |
| `company_json` | `context.company` | 企业信息 |
| `time_from` / `time_to` | 请求 context | 采集侧时间窗提示 |
| `query_hint` | 请求或默认 | 检索意图 |
| `history_events_json` | 请求或 worker prepare | 同企业历史事件摘要（已按商机族去重） |
| `max_*` / `knowledge_*` | 请求（兼容） | v3 工具链不依赖这些配额 |
| `evidence_briefs` / `discarded_briefs` | 占位 `[]` | 防止旧模板残留花括号 |

---

## 7. 输出解析

`resolve_scores_from_flow_result` 的优先级：

```text
1. edges_var.radar_event_scores / radar_event_score
2. persistence_edges_var.radar_event_scores / radar_event_score
3. 最后一条 AI 文本中的 JSON
```

兼容形态：

- `{"radar_event_scores": [ {...}, ... ]}`：多事件；
- `{"radar_event_score": {...}}`：旧单事件；
- 顶层共享 `evidences` / `discarded`：注入到每个事件；
- AI 文本可能带 Markdown 代码围栏 / 前缀说明：先提取 JSON 对象。

解析后每个事件都经过 `RadarEventScoreResult` 校验；非法分值 / 结构会抛错，路由返回 500。

---

## 8. 代码锚点

```text
backend/app/api/routes/huayuan_radar_event.py
backend/app/api/schemas/huayuan_radar_event.py
backend/domain/flows/manager.py
backend/domain/flows/builder.py
backend/domain/flows/parser.py
backend/domain/flows/condition_evaluator.py
backend/domain/flows/nodes/agent_creator.py
backend/domain/flows/nodes/function_creator.py
backend/domain/flows/implementations/radar_rule_gate_node.py
backend/domain/tools/deepseek_search_tool.py
backend/domain/tools/region_lookup_tool.py
backend/domain/tools/huayuan_radar_event_context.py
backend/infrastructure/llm/client.py
backend/infrastructure/llm/providers/manager.py
config/model_providers.yaml
config/flows/huayuan_radar_event_agent_v3/flow.yaml
config/flows/huayuan_radar_event_agent_v3/prompts/radar_event_v3.md
config/flows/huayuan_radar_event_agent_v3/prompts/radar_event_audit_v3.md
```
