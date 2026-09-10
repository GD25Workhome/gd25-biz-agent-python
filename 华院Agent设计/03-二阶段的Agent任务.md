# 功能思路
 - 基线【产品提供-260903】产品文档下的，客户雷达展厅项目需求判定规则的逻辑实现。
 - 实现的目标，实现一个Agent，暴露同【/Users/shuxiaolong/work/github/gd25WorkHome/gd25-biz-agent-python/backend/app/api/routes/huayuan_portrait.py】的类型Agent，供调用者使用
    - 细节1：独立的API，绑定固定的Agent流程。
    - 细节2: agent封装AnySearch作为搜索工具，去网络上搜索可信的源，来评分，确认公司的展厅意愿
    - 细节3: 最终输出的结果要能够支持调用者进行后续的产品流程，有评分，需要给出评分证据——为何这么打分，判定信息的来源是啥

- 入参：企业的基础信息，巨潮这类网站上的上市公司代码和name，比如：300378、鼎捷数智

- 当前的工具先只用AnySearch，需要探索AnySearch返回的数据结果是否有来源，判定来源的权威性（需要实验后判定）
    - 得到结果内容需要抽取其内容是否准确，如果内容不对，需要排除


# 详细设计

> **文档状态**：Agent 侧详细设计草案（对齐 exhibition《03-展厅【规则二】技术设计》定案 + 产品规则二 §3）。  
> **编码前置**：先评审本章「待确认问题」与契约；契约冻结后再开 Agent 侧代码。  
> **对齐文档**：
> - 产品：`产品提供-260903/数字文旅商机中心可配置规则设计v2.md` §3
> - 业务端：exhibition `03-展厅【规则二】技术设计.md` §6
> - AnySearch 调研：exhibition `0301-AnySearch调研.md`
> - 形态参考：本仓库 `huayuan_portrait`（独立 API + 固定 Flow + ReAct）

---

## 0. 定案摘要（读完可开工方向）

| 议题 | 定案 |
|------|------|
| 主问题 | 对给定企业基础信息：Agent 用 AnySearch 自查公开证据 → 输出**两维分 + 证据链**；调用方（exhibition）再按 §3.5/§3.2 **定 S 级** |
| API 形态 | 独立 `POST`，无 Session；固定绑定本流程（同 portrait 类型） |
| 证据通道 V1 | **仅 AnySearch**；不灌巨潮正文；全部证据 `source_level=P2`，调用方默认待核验 |
| Agent 职责 | **出分 + 证据 + 准入相关事实字段**；**不定最终 S1–S4** |
| 调用方职责 | 分数→S、§3.2 封顶/失效/待核验、落库与人工核验 |
| 来源权威性 | V1 做**启发式分级 + 可观测字段**；最终权威性以人工核验为准（实验后再收紧规则） |
| 内容准确性 | Agent 提示词 + 工具后处理共同做**主体/展厅相关性过滤**；不准的结果标记 discard，不得入证据 |

---

## 1. 目标与边界

### 1.1 目标

实现 `POST /api/v1/huayuan/radar-event-score`（名称见待确认-Q1），使 exhibition 规则二 job 可真实调用：

1. 入参为企业基础信息（至少：标准名、证券代码；可选别名、行业、地区、时间窗）。
2. Agent ReAct 调用 AnySearch 检索「展厅/展示中心/体验中心/招采/立项…」相关公开信息。
3. 对命中结果做**来源可追溯**与**内容可用性过滤**，再按产品 §3.4 输出**离散档位分**与证据。
4. 响应强类型，足以支撑调用方：落证据、算总分、映射候选 S、进入核验台。

### 1.2 边界（V1 不做）

- 不定最终 S1–S4（禁止把 `suggested_level` 当权威）
- 不灌巨潮公告全文/列表；不做向量库
- 不接入第二搜索源（招投标站定向爬虫等）
- 不做日频调度、行动级推送、企微
- 不修改 `/huayuan/chat`、`/huayuan/portrait` 行为
- 不把 AnySearch 结果当作可自动发布的 P0 证据

### 1.3 端到端职责

```text
【exhibition】                              【gd25-biz-agent-python】
radar_event_job/run
  组装 company + time 窗  ──────────────►  POST /huayuan/radar-event-score
        │                                        │ ReAct
        │                                        ├─ anysearch_web_search
        │                                        └─（可选）anysearch_extract
        │◄── score + evidences + flags ──────────┤
  LevelMapper（§3.2/§3.5）→ 落库 → 核验门控
```

---

## 2. 总体方案

沿用「外层 LangGraph 单节点 + 内层 LangChain `create_agent` ReAct」：

```
exhibition RadarEventAgentClient
  │  POST /api/v1/huayuan/radar-event-score
  │  Body: query + context（公司基础信息）
  ▼
huayuan_radar_event 路由（无 Session）
  │  校验 → 注入 RuntimeContext（搜索次数/Key/zone）
  │  prompt_vars ← company / time / 搜索次数等
  ▼
FlowManager.get_flow("huayuan_radar_event_agent")
  ▼
radar_event_react_node
  │  构造约束查询（公司名/代码 + 展厅意图词）
  │  AnySearch → 过滤主体/展厅相关/噪声 → 必要时 extract
  │  对齐 §3.4 选档计分 → 输出结构化 JSON
  ▼
解析并返回 { trace_id, radar_event_score }
```

与 portrait 的关键差异：

| 对比项 | portrait | 本 Agent（规则二） |
|--------|----------|-------------------|
| 工具 | 按 `file_id` 拉业务库正文 | AnySearch 联网检索（+ 可选 extract） |
| 输出 | 五维 **tier**（不出分） | 两维 **离散分** + 证据（不出最终 S） |
| Context | 含 `file_metas` / prefill | 仅公司主数据 + 可选时间窗 |
| 证据权威 | 业务侧已入库文档 | 开放搜索 P2，默认需核验 |

---

## 3. API 设计

### 3.1 接口

| 项 | 值 |
|----|----|
| Method/Path | `POST /api/v1/huayuan/radar-event-score`（待确认-Q1） |
| Tag | `华院联通` |
| Content-Type | `application/json` |
| 鉴权 | V1 无业务登录（与 chat/portrait 一致）；依赖内网/网关 |
| 超时预期 | 调用方建议 **180s**（AnySearch 多轮可能较慢）；工具单次 HTTP 建议 20–30s |

### 3.2 请求体

顶层：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 任务提示；exhibition 可写死口径，或传「请按规则二评估展厅项目需求」 |
| `context` | object | 是 | 见下表 |
| `trace_id` | string | 否 | 未传则服务端 `secrets.token_hex(16)` |

`context` 字段（对齐 exhibition §6.2，字段名用 snake_case 以便本服务统一）：

| 字段 | 必填 | 说明 |
|------|------|------|
| `company` | 是 | 见下 |
| `time_from` / `time_to` | 否 | ISO 日期；提示 Agent 关注窗口（不保证搜索引擎严格过滤） |
| `query_hint` | 否 | 默认内置展厅意图词；可覆盖 |
| `event_job_id` | 建议有 | 透传可观测，不对搜索逻辑强耦合 |
| `max_search_times` | 否 | 默认 **3** |
| `max_extract_times` | 否 | 默认 **2**；`extract` 用于 snippet 不足时拉页 |
| `max_results_per_search` | 否 | 默认 **5**（AnySearch 上限 10） |

`company`：

| 字段 | 必填 | 说明 |
|------|------|------|
| `company_id` | 建议有 | 业务侧 id |
| `company_name` | 是 | 标准名，如「鼎捷数智」 |
| `stock_code` | 建议有 | 如 `300378`；检索与主体校验用 |
| `aliases` | 否 | 别名数组 |
| `industry` / `region` | 否 | 辅助消歧 |

请求示例：

```json
{
  "query": "请根据公开信息评估该公司展厅新建/翻新/升级项目需求证据强度，并给出评分与证据。",
  "trace_id": "可选",
  "context": {
    "event_job_id": 1001,
    "company": {
      "company_id": 12,
      "company_name": "鼎捷数智",
      "stock_code": "300378",
      "aliases": ["鼎捷软件"]
    },
    "time_from": "2025-01-01",
    "time_to": "2026-09-09",
    "max_search_times": 3,
    "max_extract_times": 2
  }
}
```

**校验规则**：

- `query`、`company.company_name` 去空白非空，否则 422
- `stock_code` 缺失不阻断，但提示词应降低主体置信、倾向保守
- AnySearch Key 缺失：允许匿名调用并打 warn；配额不足时工具返回明确错误（不崩进程）

### 3.3 响应体

```json
{
  "trace_id": "a1b2c3...",
  "radar_event_score": {
    "exhibition_related": true,
    "subject_confidence": "high",
    "space_object": "企业展厅",
    "action": "升级改造意向",
    "place": null,
    "time_text": "2026年",
    "evidence_score": 60,
    "specificity_score": 10,
    "total_score": 70,
    "tags": ["升级改造"],
    "expired_or_done": false,
    "fact_status": "inferred",
    "admission_hint": "pass",
    "score_reason": "公开信息明确表达展厅升级需求，但未见立项/招采；主体匹配公司名与证券代码相关报道。",
    "evidences": [
      {
        "title": "...",
        "summary": "...",
        "quote": "短摘≤200字",
        "url": "https://...",
        "publish_date": null,
        "source_host": "example.com",
        "authority_tier": "media",
        "kept": true
      }
    ],
    "discarded": [
      {
        "title": "...",
        "url": "https://...",
        "reason": "展会临时展位，非长期展厅空间"
      }
    ],
    "search_count": 2,
    "extract_count": 1
  }
}
```

| 字段 | 说明 |
|------|------|
| `exhibition_related` | 是否与展厅/长期展示接待空间**明确相关**（§3.2 准入） |
| `subject_confidence` | `high` \| `medium` \| `low` \| `unknown` |
| `evidence_score` | **仅允许** §3.4.1 合法档：`85/75/60/45/25/10`；不准入/失效时可为 `null` |
| `specificity_score` | **仅允许** `15/10/5/0` |
| `total_score` | 建议两维之和；调用方可重算；失效/不准入为 `null` |
| `expired_or_done` | 项目完成/取消/招采窗口关闭等 |
| `fact_status` | `confirmed` \| `inferred` \| `unknown` \| `conflict` |
| `admission_hint` | 建议：`pass` \| `reject_unrelated` \| `pending_verify` \| `expired`（**提示**，最终闸门在调用方） |
| `score_reason` | 为何打这些分（给人核验读） |
| `evidences` | 有分必有据；每条可点开 URL |
| `discarded` | 被排除的命中（可观测，便于调提示词） |
| `authority_tier` | 见 §6.4；**启发式，非法律效力分级** |

**禁止**：把最终 `S1–S4` 当作权威输出字段。调试可带 `suggested_level`，调用方必须忽略。

**解析失败**：模型未吐合法 JSON → HTTP 500（与 portrait R1-a 一致），便于 exhibition job 记 FAILED 重试。

---

## 4. 产品口径（提示词真源 · 规则二 §3）

### 4.1 Agent 要判断什么

不是模糊的「展厅意愿」，而是：

> 公开信息中，该公司**展厅项目需求证据有多强**（推进阶段）+ **信息是否具体**。

### 4.2 定级前提（Agent 必须先判，再计分）

写入提示词硬约束（产品 §3.2）：

1. 未出现展厅/展馆/展示中心/体验中心/明确长期展示接待空间 → `exhibition_related=false`，**不计分**，`admission_hint=reject_unrelated`
2. 仅总部/基地/园区/品牌动态且无展厅关联 → 同上
3. 主体无法确认 → `subject_confidence=unknown`，`admission_hint=pending_verify`，**不硬打 S4 分**
4. 项目已完成/取消/窗口关闭 → `expired_or_done=true`，`admission_hint=expired`，`total_score=null`
5. 无明确项目动作时，即使两维加总偏高，**evidence_score 不得虚高到暗示 S1**（最终封顶由调用方做；Agent 侧按档位表诚实选档）

### 4.3 证据强度档（85 分，互斥取最高）

| 公开信息情况 | `evidence_score` |
|--------------|------------------|
| 明确计划（目标/范围/时间）但未立项 | 85 |
| 已立项/审批/预算/建设安排，未定设计实施单位 | 75 |
| 明确需求/意向，尚无具体计划 | 60 |
| 方案征集/供应商招募/招标采购且在有效期 | 45 |
| 新总部/基地等潜在信号且与展厅明确关联 | 25 |
| 旧展厅老化等问题，尚未提改造需求 | 10 |
| 已定实施单位/已签约/实施中且无新合作窗口 | 10 |
| 已完成/取消/招采结束 | —（失效） |
| 未发现需求或潜在信号 | —（不准入） |

### 4.4 信息具体程度（15 分）

| 情况 | `specificity_score` |
|------|---------------------|
| 主体、展厅对象、动作、地点、时间基本明确 | 15 |
| 主体、对象、动作明确，缺部分细节 | 10 |
| 仅有主体 + 展厅相关事实，需求尚不清 | 5 |
| 只有关键词，无法确认具体事件 | 0 |

### 4.5 事件标签（不计分）

`tags` 可选：`展厅立项/招标`、`升级改造`、`设计/实施单位征集`、`新总部/基地/园区`、`数字化升级`、`旧展厅老化迹象` 等（产品 §3.6）。

---

## 5. 工作流设计

### 5.1 流程标识

- **flow key**：`huayuan_radar_event_agent`
- **目录**：`config/flows/huayuan_radar_event_agent/`
- **形态**：单 `agent` 节点 + tools + END

### 5.2 flow.yaml（草案）

```yaml
name: huayuan_radar_event_agent
version: "1.0"
description: "华院规则二：ReAct + AnySearch + 展厅需求两维评分"

nodes:
  - name: radar_event_react_node
    type: agent
    config:
      prompt: prompts/radar_event_react.md
      model:
        provider: doubao
        temperature: 0.2
        thinking:
          type: disabled
      tools:
        - anysearch_web_search
        - anysearch_extract

edges:
  - from: radar_event_react_node
    to: END
    condition: always

entry_node: radar_event_react_node
```

`config/flow_loader.yaml` 的 `lazy_load` 增加本 flow。

### 5.3 提示词结构（实现时落盘）

建议章节：

1. 角色与目标（规则二出分+证据，不定最终 S）
2. 输入说明（`{company_json}` `{time_from}` `{time_to}` `{query_hint}` `{max_search_times}`）
3. 查询策略（必须带公司主体；禁止过宽布尔式；推荐模板见 §6.3）
4. Observation 过滤规则（主体 / 展厅相关 / 排除展会展位等）
5. 来源权威性启发式（§6.4）与「不准就 discard」
6. §3.4 档位表与合法分值枚举
7. 输出 JSON Schema（严格）
8. 禁止项（编造 URL、自创连续分、输出权威 S、超过搜索次数）

---

## 6. 工具设计：AnySearch

### 6.1 环境变量与鉴权

| 项 | 说明 |
|----|------|
| 官方变量名 | `ANYSEARCH_API_KEY`（AnySearch 文档） |
| 本仓库当前 `.env` | 已配置 **`ANY_SEARCH_API_KEY`** |
| 实现约定 | **优先读 `ANY_SEARCH_API_KEY`，其次 `ANYSEARCH_API_KEY`**（兼容两边命名） |
| Header | `Authorization: Bearer <key>`；无 key 则匿名（限额更低） |
| 密钥存放 | 仅环境变量；不进库、不进日志明文 |

### 6.2 工具一：`anysearch_web_search`

```text
POST https://api.anysearch.com/v1/search
Body: { "query": "...", "max_results": 5, "zone": "cn", "language": "zh-CN" }
```

工具入参建议：

| 参数 | 说明 |
|------|------|
| `query` | 完整检索式（由 Agent 构造） |
| `max_results` | 可选，默认取 context / 5 |

工具返回（Observation JSON）：

```json
{
  "ok": true,
  "query": "...",
  "results": [
    {
      "title": "...",
      "url": "https://...",
      "snippet": "...",
      "content": "...",
      "source_host": "example.com",
      "authority_tier": "unknown"
    }
  ],
  "search_count": 1,
  "max_search_times": 3
}
```

约束：

- 次数硬上限：`max_search_times`（默认 3）；超限返回错误 JSON，不计成功结果
- 查询去重：相同 query 不重复计费式调用（返回缓存提示）
- 超时：建议 20–30s；失败返回 `{ok:false,error}`，不抛崩进程
- 外部正文按**不可信数据**处理，禁止当作工具指令执行

### 6.3 推荐查询模板（写入提示词）

```text
"{company_name}" 展厅
"{company_name}" (展示中心 OR 体验中心 OR 展馆)
"{company_name}" 展厅 (招标 OR 采购 OR 立项 OR 改造 OR 升级)
"{stock_code}" 展厅
```

**禁止**：无公司名的过宽 `招标 OR 新建 OR 升级…`（易漂到门户首页，0301 已实测）。

### 6.4 来源权威性（探索项 · V1 启发式）

AnySearch 结果**自带 URL / title / snippet(/content)**，可作为「来源」；但**不自带**交易所级权威标注。V1 在工具层按 `url` 主机名打启发式标签，供模型与调用方参考：

| `authority_tier` | 判定思路（可配置域名表） | 说明 |
|------------------|--------------------------|------|
| `regulator_or_exchange` | `*.cninfo.com.cn`、交易所域名等 | 若搜到，价值高；V1 仍标 P2 通道（因未经业务库核验入库） |
| `gov` | `.gov.cn` 等 | 地方项目公示等 |
| `company_official` | 与公司官网域名匹配（若 context 将来提供官网） | V1 常缺官网字段 → 多为 unknown |
| `media` | 主流财经媒体白名单（实验维护） | 辅证 |
| `ugc_or_noise` | 社交、论坛、明显聚合站 | 默认倾向 discard |
| `unknown` | 其他 | 需更严的内容校验 |

**重要**：V1 **所有** AnySearch 证据对调用方仍声明 `source_type=anysearch`、`source_level=P2`。`authority_tier` 只影响 Agent 采信权重与核验优先级，**不**自动升为 P0。

> 用户要求「探索返回结果是否有来源、判定权威性」→ 本设计用 **URL 可追溯 + 主机名启发式 + 实验白名单** 落地；白名单效果需联调样本后迭代（待确认-Q3）。

### 6.5 内容准确性过滤（不准则排除）

过滤分两层：

**A. 工具/路由可做的轻量规则（确定性）**

- URL 无有效 http(s) → discard
- title/snippet 完全不包含 `company_name` / `stock_code` / 任一 alias → 标记 `subject_mismatch`（默认可 discard，或留给模型二次看）
- 明显二进制/PDF 且只能 extract 失败 → 保留 snippet，不强制 extract

**B. Agent 提示词必须排除的语义噪声（0301 已见）**

- 展会临时展台 / 门店装修 / 普通维修
- 与本公司无关的同名主体
- 纯行情页、首页导航、无事实正文
- 「展厅」仅作为募投长文顺带功能列举、且无新建翻新招采事实 → 最多潜在信号档，不可抬到明确需求档

过滤结果写入响应 `discarded[]`，**不得**进入 `evidences`，也**不得**支撑加分。

### 6.6 工具二：`anysearch_extract`（可选但建议有）

```text
POST https://api.anysearch.com/v1/extract
Body: { "url": "..." }
```

- 当 snippet 不足以判断「是否明确需求/是否招采有效期」时使用
- 次数上限 `max_extract_times`（默认 2）
- **不支持 PDF/Office**；失败则退回 snippet，降低 `fact_status` 或保守选档
- 返回 Markdown/正文截断（建议 ≤12000 字，与 portrait 截断理念一致）

### 6.7 RuntimeContext（请求级）

参考 `HuayuanPortraitContext`，新增 `HuayuanRadarEventContext`：

- 保存 company、次数计数、已搜 query 集合、已 extract URL 集合
- 通过 contextvar 注入，供工具读取 Key / 计数 / 公司主体词

---

## 7. 路由与工程落点

| 落点 | 说明 |
|------|------|
| `backend/app/api/routes/huayuan_radar_event.py` | 新路由 |
| `backend/app/api/schemas/huayuan_radar_event.py` | 请求/响应 Schema；合法分值校验 |
| `backend/domain/tools/anysearch_tool.py` | `anysearch_web_search` / `anysearch_extract` |
| `backend/domain/tools/huayuan_radar_event_context.py` | 请求级上下文 |
| `config/flows/huayuan_radar_event_agent/` | flow + prompt |
| `cursor_test/test_huayuan_radar_event.py` | Schema/解析/分值枚举/过滤单测 |
| `.env` | `ANY_SEARCH_API_KEY`（已有） |

路由步骤（对齐 portrait）：

1. 生成/校验 `trace_id`
2. 构建 `prompt_vars` + RuntimeContext
3. `FlowManager.get_flow(...).ainvoke`
4. 提取最后一条 AI 文本 → 解析 JSON
5. 校验合法分值枚举、有分必有 evidences、URL 非空
6. 返回强类型响应；失败 500

---

## 8. 与调用方协作契约

| 问题 | 结论 |
|------|------|
| Agent 是否输出最终 S？ | **否**；exhibition LevelMapper 为权威 |
| 仅有 AnySearch 证据能否自动发布？ | **否**；P2 + 待核验 |
| 分数不一致谁说了算？ | 调用方可对两维分做枚举校验并重算 `total_score` |
| 契约变更 | 双边同步；exhibition 可用 Mock 并行开发 |

调用方 LevelMapper 顺序（复述 exhibition 定案，供联调对照）：

```text
1. exhibition_related=false → 不准入
2. subject 不明 → 待核验，不直接当 S4
3. expired_or_done → 已失效
4. 采纳/校验两维分 → total
5. §3.5 映射 S
6. §3.2 封顶
7. 证据均 P2 → 强制待核验；S1/S2 不得自动 published
```

---

## 9. 验收用例（Agent 侧）

| 编号 | 场景 | 期望 |
|------|------|------|
| A1 | 鼎捷数智 + 正常 Key | 能搜到结果；响应含 `evidences.url`；`search_count≥1` |
| A2 | 命中展会展位噪声 | 进 `discarded`，不抬 `evidence_score` |
| A3 | 明确「展厅升级」报道、无立项 | `evidence_score` 倾向 60 档；有 `score_reason` |
| A4 | 完全无关公司动态 | `exhibition_related=false`，分值为 null |
| A5 | 超 `max_search_times` | 工具拒绝；模型仍应输出保守 JSON，不瞎编 URL |
| A6 | 无 Key（匿名） | 可降级运行或明确报错（待确认-Q2）；不得 500 空栈 |
| A7 | 模型输出 70 分等非法连续值 | 路由校验失败 → 500 或纠错到最近合法档（待确认-Q4） |

---

## 10. 待确认问题 / 风险（有问题写这里）

### 10.1 必须先对齐（阻塞编码细节）

| ID | 问题 | 影响 | 建议 |
|----|------|------|------|
| **Q1** | API 路径最终用 `/huayuan/radar-event-score` 还是 exhibition 文档中的其它命名？ | 客户端 URL | 建议本服务统一 `/api/v1/huayuan/radar-event-score`，exhibition 客户端改指向 |
| **Q2** | 无 Key / 配额耗尽时：匿名继续 vs 直接 503？ | 稳定性 | 有 Key 走 Key；无 Key 允许匿名但打 warn；配额耗尽返回工具错误并由 job 重试 |
| **Q3** | `authority_tier` 域名白名单谁维护、首版范围？ | 来源权威实验 | V1 先实现 host 解析 + 小表（cninfo/gov）；媒体白名单实验后再扩 |
| **Q4** | 非法分值：500 重试，还是服务端钳位到合法档？ | 联调体验 | 建议 **校验失败 500**（与 portrait 一致），提示词约束合法枚举 |
| **Q5** | 一次请求是返回**单条**事件结论，还是 `events[]` 多候选？ | Schema | V1 建议 **单条综合结论**（对公司当前最强证据档）；多事件后置 |
| **Q6** | `context` 字段名 camelCase（exhibition 草案）还是 snake_case？ | 对接成本 | 建议本 API 用 snake_case；exhibition 客户端做映射 |

### 10.2 产品 / 证据风险（不挡搭骨架，挡「自动定级」预期）

| ID | 问题 | 说明 |
|----|------|------|
| **R1** | 仅 AnySearch = P2 | 不能支撑自动发布 S1/S2；与「可信源评分」话术需一致：是**可追溯线索**，不是终裁 |
| **R2** | 「展厅」语义漂移 | 展会 booth、募投顺带提及 → 必须靠过滤 + 准入，否则虚高 |
| **R3** | 时间窗无法由搜索引擎严格保证 | `time_from/to` 仅提示；过期判断依赖模型读日期，易错 → `fact_status` 保守 |
| **R4** | extract 不支持 PDF | 招采 PDF 原文可能抽不到 → V1 证据偏网页新闻；巨潮后置增强 |
| **R5** | 环境变量名不一致 | `.env` 为 `ANY_SEARCH_API_KEY`，官方为 `ANYSEARCH_API_KEY` → 实现双读，文档写清 |

### 10.3 与功能思路原文的口径修正

| 原文表述 | 设计修正 |
|----------|----------|
| 「确认公司的展厅意愿」 | 改为「评估展厅**项目需求证据强度**（规则二 §3）」 |
| 「搜索可信的源来评分」 | V1 源默认 P2；可信度=URL 可追溯 + 启发式权威档 + **人工核验** |
| 「内容不对需要排除」 | 落地为 `discarded[]` + 不得入证据/计分 |

---

## 11. 建议实现顺序

1. **冻结** §3 请求/响应 Schema（与 exhibition 对表）  
2. 实现 `anysearch_*` 工具 + 双读 Key + 次数限制（可用脚本对「鼎捷数智 / 300378」做搜索抽样，验证来源字段）  
3. 新路由 + flow + 提示词（先 Mock 工具测 JSON 契约）  
4. 真联调 AnySearch；根据 `discarded` 分布调提示词与域名表  
5. exhibition 接真 Agent；验收 A1–A7 + 业务 C1–C7  

---

## 12. 本章结论

1. **可做**：独立 API + ReAct + AnySearch 工具 + 两维离散分 + 证据 URL，技术路径清晰。  
2. **必须坚持**：Agent 出分与证据；调用方定 S 与核验；AnySearch 证据 V1 全部按 P2。  
3. **探索项已设计化**：来源用 URL/`source_host`/`authority_tier` 表达；不准内容进 `discarded`。  
4. **编码前先定**：Q1/Q5/Q6（路径与 Schema），并接受 R1 的产品预期。  
