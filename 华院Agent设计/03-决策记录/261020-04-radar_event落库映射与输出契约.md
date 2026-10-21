---
date: 261020
---

# `radar_event` / `radar_event_evidence` 落库映射 与 Agent 输出契约

> **状态（2026-10-20）**：决策已落地。本文保留决策过程与坑；当前实现口径以 `华院Agent设计/02-技术设计/02-评分、自检与落库规则.md` 与代码为准。文中“待裁定 / 未实现 / 讨论稿”等措辞如与代码冲突，以代码为准。

> 定位：从 **Python 侧**讲清三件事 —— ① 两张表的**关联关系与核心字段**；② 它们**怎么对接 agent 的返回结果**（模型字段 → DB 列）；③ **真实 agent 输出里的关键字段**核对结果。
> 关联：原信号时间现状梳理已删除（见 git 历史）；原缺陷与修复记录已删除（见 git 历史）。

---

## 1. 关联关系（`radar_event` 1—N `radar_event_evidence`）

```
radar_event (1)  ──event_id──▶  radar_event_evidence (N)      # 物理外键（event_id）
   │
   ├─ score_items_json.[].evidence_nos      ─┐
   ├─ signal_time_evidence_no               ─┼─▶ 都指向"证据在本次 run 里的序号 evidence_no（从 0 起）"
   └─ evidences[].evidence_no（模型输出）     ─┘
```

- **物理关联**：`radar_event_evidence.event_id = radar_event.id`。
- **语义关联**：**三个"序号引用"**都指 `evidence_no`（**事件内序号，不是 DB id**）：
  - `score_items_json[].evidence_nos`（分项 → 哪几条证据）；
  - `signal_time_evidence_no`（信号时间 → 哪条证据）；
  - `evidences[].evidence_no`（模型给证据编的号，落库时**丢失** → 见 §4）。
- ⚠️ `replace_evidences` 是**先删后插**（重跑会换 `id`）→ 所以**不能**用 `evidence.id` 当"序号"，必须用 `evidence_no`。

---

## 2. `radar_event`：核心字段与来源（`radar_event_store._event_columns`）

| 分类 | 列 | 来源 |
|---|---|---|
| **① 直接来自模型** | `space_object` `event_name` `parent_event_id` `action` `place` `time_text` `signal_summary` `signal_time` `signal_time_evidence_no` `subject_confidence` `admission_hint` `evidence_score` `specificity_score` `total_score` `score_reason` `fact_status` `expired_or_done` `target_scope` `suggested_level` `suggested_level_reason` `procurement_scope` `event_stage` `exhibition_stage` `is_potential` `signal_category` `verify_priority_default` `verify_priority_adjusted` `verify_priority_reason` `planned_time` `expected_time` `actual_time` `date_precision` `rule_version` `tags→event_tags_json` `score_items→score_items_json` `exhibition_related`(bit) | `RadarEventScoreResult.*` |
| **② 代码派生** | `system_level` `final_level` `validity_status` `verify_status` `admission_pass` `admission_reason` | `_resolve_level_verify_admission(score, outcome)`（自检结果） |
| **③ 代码写死** | `published = 0` | 新事件默认未发布（**注意**：该列会被 UPDATE 覆盖，故已停用 UPDATE） |
| **④ 区域列**（`region_resolve`） | `region_id` `region_name` `region_path_ids` `country_id` `is_domestic` `region_source` | `resolve_event_region(place, company, place_region_id)`；`region=None` 时不写（保留人工值） |
| **⑤ 元信息** | `company_id`（来自 job）`event_job_id`（= job.id）`agent_trace_id`（= trace_id）`updater` | 代码 |
| **⑥ DB 侧** | `id` / `tenant_id` / `creator` / `create_time` / `update_time` | `insert_event` 填 |

**关键点**
- `event_name` / `parent_event_id` 是 **261020 新增列**（多事件 / 归族）；`parent_event_id` 由 **代码算族根**后写入（不直接信模型）。
- 分值/等级**不是**直接落模型原值：`system_level/final_level` 由**自检 `check()`** 的区间结果决定（模型只给 `suggested_level`）。

---

## 3. `radar_event_evidence`：列 ↔ `evidences[]` 映射（`replace_evidences`）

> 规则：**只落 `kept=true` 的证据**；先删后插（幂等）。

| 表列 | 来源（模型 `evidences[]`） |
|---|---|
| `event_id` | 本次事件 id（代码） |
| `title` / `summary` / `quote` / `source_url` / `publish_date` / `source_host` / `authority_tier` | 同名（`url→source_url`） |
| `source_type` | `ev.source_type or "web"` |
| `source_level` | `ev.source_level or "P2"`（大写） |
| `kept` | **恒 1**（未 kept 的直接跳过不落） |
| `creator` / `create_time` / `updater` / `update_time` / `tenant_id` | 代码 |

**落库与模型输出的字段差（261020 按真实数据核对后的结论）**

| 字段 | 表里有列？ | 模型给了吗 | 落库了吗 | 结论 |
|---|---|---|---|---|
| **`evidence_no`** | ❌ **无列** | ✅ 给了（`0..n-1`） | ❌ | **契约未落地**：库里没存。但 v3 实测**行序与模型顺序 1:1**（全 `kept=true`）→ **可由行序派生**（见 §5.1） |
| **`cite_reason`** | ✅ 有列 | ✅ 给了（几乎每条都有） | ❌ **NULL** | **真丢数据（v3 回归）**：老 Java 路径**写了**（老库 57583 行非空），Python 新路径**没写** → 依据抽屉「引用原因」对新事件为空 |
| `doc_id` / `chunk_id` / `content_grade` | ✅ 有列 | ❌ **没给**（web 证据无这些） | ❌ | **不算丢**：仅知识库证据才有值 |
| `source_level` | ✅ 有列 | ❌ 没给 | ✅ 写默认 `P2` | 代码兜底，正常 |

---

## 4. Agent 输出契约（模型应产出什么）

**顶层结构**（`prompts/radar_event_v3.md` §输出）：

```
{
  "radar_event_scores": [ {事件1}, {事件2}, … ],   # 每个达标簇一条（兼容单个 radar_event_score）
  "evidences":  [ … ],                            # 整轮共享（解析层会注入每个事件）
  "discarded":  [ … ]
}
```

**每个事件的字段**（39 项，分组）：

| 组 | 字段 |
|---|---|
| 定位 | `event_ref` `event_name` `space_object` `action` `place` `place_region_id` `time_text` |
| 关联 | `event_relation` `matched_event_id` `parent_event_id` |
| 时间 | `signal_summary` `signal_time` `signal_time_evidence_no` `planned_time` `expected_time` `actual_time` `date_precision` |
| 评分 | `evidence_score` `specificity_score` `total_score` `score_reason` `score_items[]{code,score,score_reason,evidence_nos}` `suggested_level` `suggested_level_reason` |
| 准入/事实 | `exhibition_related` `subject_confidence` `admission_hint` `fact_status` `expired_or_done` `target_scope` |
| 阶段/目录 | `procurement_scope` `event_stage` `exhibition_stage` `is_potential` `signal_category` `verify_priority_default` `verify_priority_adjusted` `verify_priority_reason` |
| 其它 | `tags` `rule_version` `search_count` `extract_count` `web_hit_count` |

**证据字段**（14 项）：`evidence_no` `source_type` `doc_id` `title` `summary` `quote` `url` `publish_date` `source_host` `authority_tier` `source_level` `content_grade` `cite_reason` `kept`

---

## 5. 真实 agent 输出核对（`radar_event_job.acp_raw_json`）

| job | 事件数 | **缺失**字段 | **空值**字段 | 备注 |
|---|---|---|---|---|
| 6042 | 1 | `event_ref` `event_name` `event_relation` `matched_event_id` `parent_event_id` `place_region_id` | `signal_time_evidence_no` | 改多事件**之前**的旧契约 |
| 6045 | 1 | 同上 | `signal_time_evidence_no` `planned_time` `expected_time` | 旧契约 |
| 6046 | 1 | `event_ref` `event_name` `event_relation` `matched_event_id` `parent_event_id` | `place_region_id` `planned_time` `expected_time` `actual_time` | **跑的仍是旧提示词**（`.md` 未重载）→ 新字段还没产出 |

**证据侧（三次都一致）**：`evidences[]` 每项**都带 `evidence_no`**（首条 = `0`）✅ —— 说明**模型侧契约没问题，是落库丢了**。
> 另注：6046 的 `signal_time_evidence_no` **有值（=2）**，但 6042/6045 为空 —— 是"模型那次没给"，不是链路问题。

**结论**
1. **证据 `evidence_no` 一直有输出** → 断点在**落库/DB**（§3）；
2. **新多事件字段（`event_ref`/`event_name`/`event_relation`/`matched_event_id`/`parent_event_id`）在真实输出里还没出现** → 因为改了 `.md` 提示词但**服务没重载**（只有 `.py`/`.yaml` 变更才触发；`.md` 要手动 `touch`/重启）；
3. `place_region_id` 同理（提示词没生效 → 模型没输出；**但现在有代码兜底 B，不再依赖它**）。

### 5.1 顺序对齐 & `cite_reason` 对比（261020 实测，**重要更正**）

**① 行序 vs 模型顺序（`radar_event_evidence` 按 `id` 升序）**

| 事件 | 模型 `evidences[]` | 库里行 | 顺序对齐 | `kept=false` |
|---|---|---|---|---|
| 5640 / 5636 / 5639 | 4 / 4 / 4 | 4 / 4 / 4 | ✅ **1:1 完全一致** | 0 |
| v3 任务扫描（6041–6046、6036） | — | — | `evidence_no` 均为 `0..n-1` 连续 | 0 |

→ **当前 v3 数据里，行序 == `evidence_no`**，所以序号**可以从行序派生**，`radar_event_evidence` **本身就是证据表**（一条一行）。
⚠️ 但这是"模型当前习惯"（把未采信的写进 `discarded` 而不是 `evidences[].kept=false`）——**全库扫描（含老任务）有 90% 的证据条目是 `kept=false`**，一旦 v3 模型也这么给，**序号就会错位** → **派生不稳**，契约上仍应显式存 `evidence_no`。

**② `cite_reason`（引用原因）**

| 来源 | 模型 | 落库 |
|---|---|---|
| 老 Java 路径 | 有 | ✅ **写了**（老库 57583 行非空，样例："仅栏目页含「品牌展厅」导航词…"） |
| **v3 Python 路径** | 有（57602 条几乎全有） | ❌ **全 NULL**（5640/5636/5639 的 12 行全空） |

→ **`cite_reason` 是真丢数据，且是 v3 迁移漏写**（与"区域列漏迁"同一类：迁移 writer 未逐列核对副作用）。

---

## 6. 缺口与修法一览

| # | 缺口 | 性质 | 修法 |
|---|---|---|---|
| 1 | `cite_reason` 未落库 | **真 bug（v3 迁移漏写，数据丢失）** | ✅ **已修（261020）**：`replace_evidences` INSERT 列补 `cite_reason`（表已有列，`_EVIDENCE_MAX` 加 500 截断），**无需 DDL** |
| 2 | `evidences[].evidence_no` 前端取不到 | **契约未落地**（数据在、顺序对） | ✅ **已修（261020，方案 A）**：证据表加 `evidence_no int`（脚本 `47_radar_event_evidence_no.sql`）+ `RadarEventEvidenceDO` 加字段 + `replace_evidences` 按 kept 顺序写 `0..n-1` |
| 3 | `doc_id` / `chunk_id` / `content_grade` | 非缺口 | 模型未给（web 证据）；知识库证据恢复后再看 |
| 4 | 新契约字段未产出 | 运行态 | `touch` 一个 `.py` 或重启服务 |

### 6.1 修复验证（261020）

- **真库干跑 + 回滚**：`replace_evidences(5640, …)` 写入 2 条 → `evidence_no = 0,1`（**连续**，跳过了 `kept=false` 的那条）、`cite_reason` 落库且**按 500 截断**；回滚后事件 5640 原有 4 行完好。
- **Java**：`RadarEventEvidenceDO` 加 `evidenceNo`（VO 早已有）→ `mvn -o -pl yudao-module-radar/yudao-module-radar-biz -am -DskipTests compile` **BUILD SUCCESS**。
- **测试**：新增 `test_replace_evidences_writes_evidence_no_and_cite_reason`（含 kept=false 跳过、序号连续、cite_reason 落库）；相关 **106 passed**。
- **前端**：`#序号` 与「依据资料」关联**无需改动**即可生效（`scoreCitation.ts` / `event/index.vue` 本就按 `evidenceNo` 取）。

---

## 7. 代码锚点

| 层 | 文件 |
|---|---|
| 事件落库 | `radar_score/radar_event_store.py`（`_event_columns` / `insert_event` / `replace_evidences`） |
| 执行 | `radar_score/execute.py`（逐事件：自检 → 决策 → 落库） |
| 契约 / 解析 | `backend/app/api/schemas/huayuan_radar_event.py`、`backend/app/api/routes/huayuan_radar_event.py` |
| 提示词 | `config/flows/huayuan_radar_event_agent_v3/prompts/radar_event_v3.md` |
| 输入组装 | `radar_score/prepare.py`（company / 历史 / time window） |
| 区域列 | `radar_score/region_resolve.py` |
| 展示侧 | 原信号时间现状梳理已删除（见 git 历史） |
