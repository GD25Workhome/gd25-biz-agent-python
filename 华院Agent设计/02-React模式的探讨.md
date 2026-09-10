# 探讨逻辑

- 基于【01-第一个联通设计.md】的设计，我需要进行下一步工作的验证
- 我需要开发一个Agent 其需要有能力：调用外部接口的能力、边调用工具边思考的能力
  - 工具为：根据context中的文件id，加载文档的实际内容
  - 边查（调用工具）边思考的能力：我的业务是根据context中的内容，给公司进行五维画像的评分。但是需要设计一下Agent的能力：
    1. context的初始内容可能不够，此时需要agent调用工具加载详细的内容来辅助判断。加载次数有限制，不要加载太多无效的内容
    2. 每次加载有思考这个内容是否有价值，如果没有价值则丢弃，有价值则提取要点，压缩。（这个应该是多伦之后的context压缩，具体还需要AI考虑如何设计，前期不要太复杂，简单高效）
- 根据文件Id查询文档内容的接口是另一个服务的数据库中的数据，我会在另一个服务中封装好给你。但是这里我又个疑惑，是否可以把它里面的内容切割一下，存到向量库中，作成向量查询呢？

- 新补充资料（在应用后台进行了初步的开发工作，把新的材料补充一下）
    - 资料：
        - 【/Users/shuxiaolong/work/unidt/exhibition/projectDocs/技术设计文档-0905/详细设计/0203-画像Agent服务对接说明.md】在业务后台做了初步的接口开发，这是开发后的对接概要说明
        - 【/Users/shuxiaolong/work/unidt/exhibition/projectDocs/技术设计文档-0905/详细设计/0202-画像依赖Agent设计-工具设计.md】这是开发过程的设计文档
        - 【/Users/shuxiaolong/work/unidt/exhibition/projectDocs/产品提供-260903】这里是原始的产品设计文档，我觉得做工作流的提示词可以从产品文档中提取。当然需要做的其实是雷达这个链路中的五维画像的评分提示词，我判断是这样，供AI参考


# AI 的详细设计

> **文档状态**：已根据 exhibition 侧 0202/0203 落地实现与产品《客户雷达企业五维画像评分标准》**升级定稿草案**（相对上一版探讨稿）。  
> **编码前置**：你评审本篇无误后再开 Agent 侧代码。  
> **对齐文档**：
> - Agent 联通：`华院Agent设计/01-第一个联通设计.md`
> - 业务调用端：`0202-画像依赖Agent设计-工具设计.md`、`0203-画像Agent服务对接说明.md`
> - 产品口径：`产品提供-260903/客户雷达企业五维画像评分标准.md`

---

## 0. 相对上一版：是否需要升级？结论

**需要升级。** 业务侧已把原先「待抉择」中的主契约跑通并写死；Agent 侧若仍按占位五维 / 自创分数 / 假想文档 URL 开发，将无法对接。

| 议题 | 上一版（探讨） | 现状（业务已落地） | 本版 Agent 设计动作 |
|------|----------------|--------------------|---------------------|
| API 路径 | 待抉择 A1/A2 | **已定** `POST /api/v1/huayuan/portrait` | 按此实现，不再扩展 chat |
| 请求 context | 简化草案 | **已定** 完整字段（company / rule_prefill / file_metas.summary / document_tool_base_url…） | Schema 与 0203 §4/§5.2 **逐字段对齐** |
| 响应 | 待抉择是否强类型；曾含 score | **已定** 强类型 `portrait`；**只出档位 tier，不出分数** | 删除 score；档位枚举与 dim_code 对齐产品 |
| 五维定义 | 占位「技术力/市场力…」 | **已定** 业务表达复杂度 / 更新频率 / 预算 / 智能化 / 标杆 | 提示词按产品标准重写 |
| 文档工具 | 接口未就绪、形态待定 | **已就绪** `GET .../radar/agent/tool/document/get` | 工具按真实 URL 实现；Base URL **优先用请求 context** |
| 向量库 | 待抉择 | 双方约定 **不做** | 关闭该分支 |
| max_load / 截断 | 待抉择 | **3 次 / 12000 字**（业务配置默认） | 采用该默认；context 可覆盖 max_load_times |
| 职责切分 | Agent 打分含糊 | **规则落分在 exhibition**；Agent 只选档 + 证据 | 明确 Agent 不做总分/等级/入池 |
| 阻塞点 | Agent 未开发 | exhibition 已 mock 跑通；**等本服务 portrait** | 本仓库是当前主阻塞 |

**总体架构不变**：仍是「无 Session 的轻量 API + 单节点 ReAct + 按 file_id 拉正文」。升级的是**契约细节、产品口径、工具 URL、输出语义**。

---

## 1. 目标与边界

**目标**：实现 `POST /api/v1/huayuan/portrait`，使 exhibition 在关闭 `portrait-mock` 后可真实调用：Agent 基于「无全文」context，按需工具加载证据正文，对五维输出**候选档位 + 证据引用**；exhibition 再规则映射固定分并落库。

**本版验证重点（Agent V2）**：

- 对接真实报文（中科美菱样例可复现）
- ReAct + `load_document_by_file_id` 回调 exhibition 工具 API
- 加载次数硬上限 + 白名单 + 去重
- 提示词内「有用则要点压缩、无用则丢弃」
- 输出强类型 `portrait`（tier / fact_status / evidence）

**边界（不做）**：

- 不计算固定分值、总分、画像等级、入池建议（属 exhibition `RadarProfileRuleService`）
- 不直连业务库；不引入医疗 Session/Token 登录体系
- 不做向量检索 / 文档切块入库
- 不做 Plan-and-Execute 多节点；不做跨请求 Session 记忆
- 不修改 `/api/v1/huayuan/chat` 与 `huayuan_simple_agent`

**端到端职责**：

```text
【exhibition】                         【gd25-biz-agent-python】
profile-job/run
  组装 query+context（无全文）  ──►  POST /huayuan/portrait
        │                                │ ReAct
        │◄── GET document/get?id= ───────┤
  解析 portrait → tier→score → 落库
```

---

## 2. 总体方案

沿用「外层 LangGraph 单节点 + 内层 LangChain `create_agent` ReAct」：

```
exhibition RadarAgentClient
  │  POST /api/v1/huayuan/portrait
  │  Body: query + context（0203 契约）
  ▼
huayuan_portrait 路由（无 Session）
  │  校验 → 注入 RuntimeContext（白名单/次数/工具基址/jobId）
  │  prompt_vars ← context 序列化字段
  ▼
FlowManager.get_flow("huayuan_react_agent")
  ▼
portrait_react_node（tools: load_document_by_file_id）
  │  先看 company + rule_prefill + file_metas
  │  缺口维 → 选 file_id → 工具拉正文 → 价值判断 → 要点/丢弃
  │  收束 → 只输出档位 JSON
  ▼
解析并返回 { trace_id, portrait }
```

---

## 3. API 设计（与 0203 对齐 · 定案）

### 3.1 接口

| 项 | 值 |
|----|----|
| Method/Path | `POST /api/v1/huayuan/portrait` |
| Tag | `华院联通` |
| Content-Type | `application/json` |
| 鉴权 | V2 无业务登录（与 chat 一致）；依赖内网/网关 |
| 超时预期 | 调用方 120s；Agent 侧工具 HTTP 建议 10s |

### 3.2 请求体（定案）

顶层：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 固定任务提示（exhibition 已写死口径） |
| `context` | object | 是 | 见下表 |
| `trace_id` | string | 否 | 未传则服务端 `secrets.token_hex(16)` |

`context` 字段（与 0203 一致）：

| 字段 | 必填 | 说明 |
|------|------|------|
| `profile_job_id` | 建议有 | 传给工具作可选 `jobId` 归属校验 |
| `rule_version` | 建议有 | 如 `profile-v1`；写入日志/可观测 |
| `company` | 是 | `company_id/company_name/stock_code/industry/revenue_yi/listed` 等 |
| `rule_prefill` | 建议有 | 本服务已算的 `budget` / `benchmark` / `update_freq` 提示 |
| `file_ids` | 是 | 字符串数组；= `radar_raw_document.id`；**工具白名单** |
| `file_metas` | 建议有 | `file_id/title/hint/summary`（**不是全文**） |
| `stats` | 否 | 如 `doc_count_12m`、`cninfo_count` |
| `max_load_times` | 否 | 默认 **3**；覆盖服务默认 |
| `document_tool_base_url` | 是（联调） | 如 `http://127.0.0.1:38080/admin-api` |

请求示例（摘自 0203 中科美菱，可作联调用例）：见业务文档 §5.2；Agent 侧单测应用同等结构 mock。

**校验规则（Agent）**：

- `query` 去空白非空，否则 422
- `context.file_ids` 允许空数组（无证据仍可评；主要靠 company + prefill）
- `document_tool_base_url` 缺失时：允许用环境变量兜底；二者都无则工具调用返回明确错误（不 500 崩进程）

### 3.3 响应体（定案）

**优先结构**（exhibition 已按此解析）：

```json
{
  "trace_id": "a1b2c3...",
  "portrait": {
    "dimensions": [
      {
        "code": "biz_complexity",
        "tier": "medium",
        "fact_status": "inferred",
        "evidence": [{"ref_id": 7, "quote": "短摘≤200字"}],
        "missing_reason": null
      }
    ],
    "loaded_file_ids": ["7"],
    "discarded_file_ids": [],
    "load_count": 1
  }
}
```

| 字段 | 说明 |
|------|------|
| `trace_id` | 必返回 |
| `portrait.dimensions[].code` | 见 §4 五维编码 |
| `portrait.dimensions[].tier` | 仅 `strong` \| `stronger` \| `medium` \| `weak_or_unknown` |
| `portrait.dimensions[].fact_status` | `confirmed` \| `inferred` \| `unknown` \| `conflict`（对齐产品：已确认/系统推断/信息缺失/信息冲突） |
| `portrait.dimensions[].evidence` | `ref_id` 必须 ∈ 本次 `file_ids`（数值或可解析为文档 id）；`quote` 短摘 |
| `portrait.dimensions[].missing_reason` | 信息不足时说明；有证据可为 null |
| `loaded_file_ids` / `discarded_file_ids` / `load_count` | 可观测与落库透传 |

**兼容（可选实现）**：额外带 `response` 字符串（portrait 的 JSON 序列化），便于人工查看；exhibition 已写「`response` 为 JSON 且内含 dimensions/portrait」的兼容逻辑。  
**推荐默认**：**强类型 `portrait` 必填**；`response` 可选。解析失败（模型未吐合法 JSON）→ HTTP 500 或返回 `portrait.dimensions=[]` 并打错误日志——见【待评审-R1】。

**禁止**：在 `portrait` 中输出任意分数、总分、等级、入池建议。

---

## 4. 五维产品口径（定案 · 提示词真源）

编码与满分（落分在 exhibition；Agent 只记 code + tier）：

| dim_code | 中文 | 满分 | tier→分（业务侧） |
|----------|------|------|-------------------|
| `biz_complexity` | 业务表达复杂度 | 25 | strong=25, stronger=20, medium=10, weak_or_unknown=0 |
| `update_freq` | 内容更新频率 | 20 | 20 / 16 / 8 / 0 |
| `budget` | 预算能力 | 20 | 20 / 16 / 8 / 0 |
| `intel_potential` | 智能化潜力 | 20 | 20 / 16 / 8 / 0 |
| `benchmark` | 标杆价值 | 15 | 15 / 12 / 6 / 0 |

档位中英映射（提示词与 JSON 统一用英文枚举）：

| 产品用语 | tier |
|----------|------|
| 强 | `strong` |
| 较强 | `stronger` |
| 一般 | `medium` |
| 弱/无依据 | `weak_or_unknown` |

**与 `rule_prefill` 的协作（定案）**：

- exhibition 已对 **`budget` / `benchmark` / `update_freq`** 做规则预填，且**最终以预填覆盖 Agent 同维**。
- Agent 提示词应写明：
  1. 可将 prefill 视为高置信参考，**不要为抬分而硬改**；
  2. **重点 Recat 推理与按需加载**：服务 **`biz_complexity`、`intel_potential`**（及预填缺失/冲突时的维）；
  3. 仍建议在 `dimensions` 中带齐五维（与 prefill 一致即可），避免调用方缺字段；若某维完全交给预填，可输出与 prefill 相同 tier，`fact_status=confirmed`，evidence 可引用 company 字段说明。

**判断标准摘要（写入提示词，细节摘自产品文档）**：

1. **biz_complexity**：业务/技术/案例是否需要系统化、场景化展陈表达（多板块、复杂关系 → 强；信息不足 → weak_or_unknown）。
2. **update_freq**：近 12 个月公开动态频率（可用 `stats` + metas 的发布时间 hint；正文加载用于确认「是否有效更新」）。
3. **budget**：优先营收（≥10 亿强；2–10 较强；0.5–2 一般；更低或缺失弱）；规模仅辅助。
4. **intel_potential**：数字化/AI 战略、系统与可落场景。
5. **benchmark**：全国/行业头部、上市、专精特新等示范价值；上市只是依据之一。

执行规则（提示词硬约束）：

- 每维只选一档；多条件命中取**证据能支撑的最高档**。
- **只出档位，不自创分数**。
- 证据不足 → `weak_or_unknown` + `fact_status=unknown` + `missing_reason`。
- 来源冲突 → `fact_status=conflict`，档位谨慎（可为 weak_or_unknown），说明冲突点。

---

## 5. 工作流设计

### 5.1 流程标识

- **flow key**：`huayuan_react_agent`
- **目录**：`config/flows/huayuan_react_agent/`
- **形态**：单 `agent` 节点 + tools + END

### 5.2 flow.yaml（草案）

```yaml
name: huayuan_react_agent
version: "1.0"
description: "华院画像V2：ReAct + 证据按需加载 + 五维档位输出"

nodes:
  - name: portrait_react_node
    type: agent
    config:
      prompt: prompts/portrait_react.md
      model:
        provider: doubao
        temperature: 0.2
        thinking:
          type: disabled   # 默认；见待评审-R2
      tools:
        - load_document_by_file_id

edges:
  - from: portrait_react_node
    to: END
    condition: always

entry_node: portrait_react_node
```

`flow_loader.yaml` 的 `lazy_load` 增加 `huayuan_react_agent`。

### 5.3 提示词 `portrait_react.md` 结构（实现时落盘）

建议章节：

1. 角色与目标（客户雷达五维候选档位，不打分）
2. 输入说明（占位符：`{company_json}` `{rule_prefill_json}` `{file_metas_json}` `{stats_json}` `{max_load_times}` `{rule_version}`）
3. 五维定义与档位标准（从产品文档压缩摘录，避免全文过长）
4. 工具使用策略（白名单、次数、去重、先 meta 后全文）
5. Observation 处理（价值判断 → discard 或 ≤200 字要点；最终 evidence.quote 用要点）
6. 输出 JSON Schema（严格）
7. 禁止项（自创分、编造 ref_id、重复加载、超过 max_load_times）

占位符由路由写入 `prompt_vars`（JSON 字符串即可，避免复杂对象格式化问题）。

---

## 6. 工具设计：`load_document_by_file_id`（对齐已上线工具）

### 6.1 HTTP 约定（exhibition 已实现）

```http
GET {document_tool_base_url}/radar/agent/tool/document/get?id={file_id}&maxChars={n}&jobId={profile_job_id}
```

- `document_tool_base_url`：**优先**取本次请求 `context.document_tool_base_url`
- 环境变量兜底：如 `HUAYUAN_DOCUMENT_TOOL_BASE_URL`（可选）
- 联调期工具 `@PermitAll`；正式可能加 tool-token（预留 Header 配置，V2 可不强制）

期望 `data`：

```json
{
  "fileId": "7",
  "title": "...",
  "sourceType": "cninfo",
  "publishedAt": "...",
  "content": "...",
  "truncated": true,
  "charCount": 12000,
  "hasFullText": true
}
```

正文策略在业务侧：优先 `content_text` 截断，否则 summary，都无则空串。

### 6.2 工具函数签名

```text
load_document_by_file_id(file_id: str) -> str
```

返回 JSON 字符串（便于 Observation 解析），字段对齐上表。

### 6.3 Agent 侧硬约束（不靠提示词 alone）

| 约束 | 行为 |
|------|------|
| 白名单 | `file_id ∉ allowed_file_ids` → 返回错误 JSON，不发 HTTP |
| 次数 | `load_count >= max_load_times` → 拒绝并提示「已达上限」 |
| 去重 | 已成功加载过的 id → 提示复用要点，不二次 HTTP |
| 截断 | 请求带 `maxChars`（默认 12000）；以工具响应 `truncated` 为准 |
| 超时 | HTTP 超时（建议 10s）；失败返回可读错误，ReAct 可降级 |
| jobId | RuntimeContext 有 `profile_job_id` 则附带 query 参数 |

### 6.4 RuntimeContext 注入（定案倾向）

路由在 `ainvoke` 前注入（**不**引入登录 Session）：

- `allowed_file_ids`
- `max_load_times`
- `load_count`（可变计数）
- `loaded_ids` / `discarded` 可由工具侧只维护 loaded；discard 靠模型输出
- `document_tool_base_url`
- `profile_job_id`
- `trace_id`
- `max_chars=12000`

实现：扩展现有 `backend/domain/tools/context.py` 的 contextvars，或华院专用 `HuayuanPortraitContext`，避免污染医疗 `token_id` 语义。

### 6.5 联调风险（写入设计，非阻塞编码）

中科美菱样本大量 `content_text` 空、`fetch_status=0`。工具可能只返回 summary/空串。  
提示词须要求：无全文时基于 summary + company + stats 推断，并标 `inferred`/`unknown`，**禁止编造公告原文**。  
真实 ReAct 验证需业务侧开 PDF 抽取或补正文（0203 已说明）。

---

## 7. 「边查边想 + 压缩」方案（定案）

采用 **E1：提示词内闭环** + 工具侧已有截断：

```
每次工具 Observation：
1) 是否有助于未决维度？→ 否：记入 discarded_file_ids，后续不引用正文
2) 是：提炼 ≤200 字要点（可作 evidence.quote）
3) 禁止把整篇 content 贴进最终 JSON
```

不增压缩节点、不做工具侧二次小模型摘要（业务工具已截断 12k）。

向量库：**不做**（F1 定案）。候选约 ≤20 条 + meta/summary，足够选型。

---

## 8. 服务端处理流程（Agent）

1. 校验 `query`、`context` 基础结构。  
2. 解析/生成 `trace_id`。  
3. 从 context 读取 `file_ids`、`max_load_times`（默认 3）、`document_tool_base_url`、`profile_job_id`。  
4. `FlowManager.get_flow("huayuan_react_agent")`。  
5. 构造 `FlowState`：  
   - `current_message` = `query`（可附加「请严格输出规定 JSON」）  
   - `prompt_vars` = company / rule_prefill / file_metas / stats / max_load_times / rule_version 等 JSON 字符串  
   - `history_messages=[]`，`session_id/token_id` 空占位  
6. `with HuayuanPortraitContext(...): await graph.ainvoke(...)`  
7. 从 `flow_msgs` 取最终 AI 文本 → 解析为 `portrait`（容错：抽第一个 JSON 对象）。  
8. 服务端轻量校验：tier/code 枚举；非法降为 `weak_or_unknown` 或丢弃该维（与 exhibition 降级策略对齐）。  
9. 返回 `{ trace_id, portrait }`；可选填 `response`。

---

## 9. 代码落点清单（评审通过后实现）

| 项 | 路径 |
|----|------|
| 路由 | `backend/app/api/routes/huayuan_portrait.py` |
| Schema | `backend/app/api/schemas/huayuan_portrait.py` |
| 注册 | `backend/app/api/routes/__init__.py` |
| 流程 | `config/flows/huayuan_react_agent/flow.yaml` |
| 提示词 | `config/flows/huayuan_react_agent/prompts/portrait_react.md` |
| 工具 | `backend/domain/tools/huayuan_document_tool.py` + `init_tools()` |
| 请求上下文 | 扩展 `tools/context.py` 或新建华院 context |
| 配置 | `.env` 兜底 Base URL；`flow_loader.yaml` lazy_load |
| 测试 | `cursor_test/test_huayuan_portrait.py`（mock HTTP 工具 + mock graph） |

**不修改**：`/huayuan/chat`、`huayuan_simple_agent`。

---

## 10. 验收标准（与 0203 checklist 对齐）

1. `POST /api/v1/huayuan/portrait` 接受 0203 §5.2 形态报文，返回非 mock 的 `trace_id`。  
2. `portrait.dimensions` 使用法定 `code`/`tier`；**无自创分数**。  
3. 需要正文时出现对  
   `{document_tool_base_url}/radar/agent/tool/document/get?id=` 的调用；`load_count ≤ max_load_times`。  
4. 白名单外 id 不发 HTTP；重复加载短路。  
5. exhibition 关 `portrait-mock`，对 `company_id=5556` 新建+执行：`agent_trace_id` 非 `mock-*`；`biz_complexity` / `intel_potential` 有合理档位（有正文样例时）。  
6. 工具无正文/超时：仍返回可用 portrait（偏低置信或 weak_or_unknown），进程不崩。  
7. `/huayuan/chat` 回归不受影响。

---

## 11. 后续扩展（非本版）

- 工具鉴权 Header（tool-token）  
- 证据分段拉取 / 向量检索  
- 流式输出 Thought/Tool  
- Agent 输出与人工改档闭环  
- 有正文语料后的提示词精调

---

## 12. 上一版「待抉择」关闭清单

| 原编号 | 定案 |
|--------|------|
| A | **A1** `POST /api/v1/huayuan/portrait` |
| B | **强类型 portrait**；分数禁止；`response` 可选兼容 |
| C | **产品五维 + 英文 code/tier**；刻度由 exhibition 映射 |
| D | **D1 已就绪**：`GET .../document/get`；联调免登 |
| E | **E1** 提示词要点压缩 |
| F | **F1** 不做向量 |
| G | **G1** `max_load_times=3`，`max_chars=12000` |
| H | 默认 **H1 disabled**；是否改 H2 见待评审-R2 |
| I | **华院专用上下文**（白名单/基址/jobId/次数）；不强行假 token_id |

---

# 【评审定案】（2026-09-08）

用户确认：`R1-a R2-a R3-a R4-a R5-a`

| 编号 | 定案 |
|------|------|
| R1 | **R1-a**：portrait 解析失败 → HTTP 500 + detail |
| R2 | **R2-a**：`thinking: disabled` |
| R3 | **R3-a**：必须返回全部五维（缺维补 `weak_or_unknown` 或抄 prefill） |
| R4 | **R4-a**：联调免登录，工具不传额外鉴权 Header |
| R5 | **R5-a**：产品五维标准压缩版写入系统提示词 |

**编码状态**：Agent 侧主路径代码已落地（见下方 §13）；待与 exhibition 关 mock 做端到端联调验收。

---

# 13. 实现进度盘点（Agent 侧 · 2026-09-08）

> 对照本设计 §3–§10 与 exhibition `0203` checklist。范围仅 **gd25-biz-agent-python**。

## 13.1 已完成

| 模块 | 落地说明 | 路径 / 证据 |
|------|----------|-------------|
| Portrait API | `POST /api/v1/huayuan/portrait`；强类型 `portrait` + 可选 `response`；无 Session | `backend/app/api/routes/huayuan_portrait.py`、`schemas/huayuan_portrait.py`；已注册到 `routes/__init__.py` |
| 请求契约 | 兼容 0203 context：`company` / `rule_prefill` / `file_ids` / `file_metas` / `stats` / `max_load_times` / `document_tool_base_url` / `profile_job_id` | Schema `HuayuanPortraitRequestContext` |
| R1-a 解析失败 | 模型输出无法解析 JSON → HTTP **500** + detail | 路由 `ValueError` → 500；单测覆盖 |
| R3-a 五维齐全 | 缺维抄 `rule_prefill` 或补 `weak_or_unknown` | `ensure_all_dimensions` / `parse_portrait_from_ai_text` |
| ReAct 流程 | 单节点 `agent` + `thinking: disabled`（R2-a） | `config/flows/huayuan_react_agent/flow.yaml`；已入 `flow_loader.yaml` lazy_load |
| 提示词 | 产品五维压缩标准 + 工具策略 + 输出 Schema（R5-a） | `prompts/portrait_react.md` |
| 文档工具 | `load_document_by_file_id` → `GET {base}/radar/agent/tool/document/get`；联调无鉴权头（R4-a） | `backend/domain/tools/huayuan_document_tool.py`；`init_tools()` 已 import |
| 请求级限流 | 白名单 / `max_load_times` / 去重 / `max_chars=12000` / `jobId` 透传 | `huayuan_portrait_context.py` |
| Base URL | 优先请求 `document_tool_base_url`，否则环境变量 `HUAYUAN_DOCUMENT_TOOL_BASE_URL` | 路由 + 工具 |
| 单元测试 | Schema、上下文、解析补齐、工具 mock、API 成功/500 | `cursor_test/test_huayuan_portrait.py`（8 passed） |
| 联通基线保留 | `/huayuan/chat` + `huayuan_simple_agent` 未改职责 | 仍独立可用 |

## 13.2 未完成

| 模块 | 说明 | 建议下一步 |
|------|------|------------|
| **与 exhibition 真实联调** | Agent 接口已有；业务侧当前默认 `portrait-mock=true`，真实 HTTP + 工具回调闭环**尚未在联调环境验收** | 关 mock → 样例公司新建+执行 → 核对非 `mock-*` trace |
| **有正文样例上的 ReAct 质量验证** | 中科美菱等样本常无 `content_text`；工具回调价值与档位合理性未用真实正文跑通 | 开 PDF 抽取或补正文后再验 `biz_complexity` / `intel_potential` |
| **`.env` 兜底配置落盘** | 代码支持 `HUAYUAN_DOCUMENT_TOOL_BASE_URL`，仓库 `.env` **尚未写入**该项 | 联调机按需补充；有请求内 base_url 时可缺省 |
| **工具正式鉴权** | R4-a 定案联调免登录；tool-token / 租户头未实现（设计 §11 后置） | 正式环境前再做 R4-b |
| **端到端自动化测试** | 仅有 mock 单测；无对真实 LLM + 真实 document/get 的集成测试 | 可选：录制回放或 staging 冒烟脚本 |
| **提示词精调** | 首版压缩标准已写入；未根据真实模型输出迭代 | 联调看非法 JSON / 漏维 / 乱加载频率后再改 |
| **向量 / 分段拉取 / 流式 Thought** | 明确非本版 | 保持不做 |

## 13.3 风险与不确定项

| ID | 风险 / 不确定 | 影响 | 缓解 |
|----|---------------|------|------|
| U1 | **证据无全文**（采集未抽 PDF） | ReAct「加载」常得空串/summary，复杂度与智能化档位易偏 `weak_or_unknown` / 低置信 | 样例开 `RADAR_CNINFO_FETCH_PDF` 或补 `content_text`；提示词已禁止编造原文 |
| U2 | **模型不守 JSON** | 触发 R1-a → 整次 job **500/FAILED**（相对宽松空维更刺眼） | 联调盯 Langfuse/日志；稳定后可评估改 R1-b |
| U3 | **同步 run 超时**（业务侧 120s） | 多次工具 + LLM 可能超时 | 控制 `max_load_times=3`；必要时升超时或后续异步 |
| U4 | **跨机调工具网络/租户** | Agent 与 exhibition 不在同机时，`document_tool_base_url` 须可达；免登无租户头可能查不到数 | 联调约定可达 URL；正式加鉴权/租户 |
| U5 | **prefill 与 Agent 同维冲突** | 业务最终覆盖 budget/benchmark/update_freq；Agent 乱改无最终效力但浪费加载额度 | 提示词要求勿硬改 prefill；重点加载后两维 |
| U6 | **非法 tier/code** | 已做档位归一与五维补齐；极端脏输出仍可能 500 | 单测覆盖主路径；联调观察 |
| U7 | **首次编译延迟** | `huayuan_react_agent` 为 lazy_load，首请求可能偏慢 | 可选改 preload；或接受冷启动 |
| U8 | **验收项 5/6 未闭环** | §10 中「关 mock 真实跑中科美菱」「无正文仍可用 portrait」依赖联调，代码侧无法单凭单测宣称完成 | 以 exhibition 关 mock 的一次成功 run 为完成门禁 |

## 13.4 建议联调顺序（完成门禁）

1. Agent 服务就绪（reload 后 OpenAPI 可见 `/api/v1/huayuan/portrait`）。  
2. exhibition：`portrait-mock: false`，核对 `radar.agent.base-url` 与 `document-tool-base-url`。  
3. curl 或前端对**有正文**样例「新建+立即执行」。  
4. 核对：`agent_trace_id` 非 `mock-*`；`portrait.dimensions` 五维齐全；必要时日志中出现 `document/get`。  
5. 再跑无正文样例，确认不崩且多为 `inferred`/`unknown`。

**当前结论**：Agent 侧设计范围内的**主开发切片已完成**；**产品可验收状态**取决于 exhibition 关 mock 后的端到端联调（§13.2 / U8）。

