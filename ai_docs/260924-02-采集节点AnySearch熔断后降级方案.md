---
date: 260924
---

# 采集节点：AnySearch 熔断后的降级

**文档编号**：260924-02
**类型**：改造方案
**对象**：`backend/domain/flows/implementations/radar_evidence_gather_node.py` 的 `EvidenceGatherNode`
**结论一句话**：图的边保持 `query_planner → evidence_gather → score_summarizer` 全是 `always`。凭证池没有存活 key 时，采集节点不再扇出 AnySearch；博查和知识库照常产出 briefs，终评照常执行。换 key 仍由工具层完成（见 `260924-01-AnySearch工具层凭证池故障转移方案.md`）。

---

## 0. 这一层在做什么

工具层保证：还有存活 key 时，单次 `anysearch_web_search` / `anysearch_extract` 自己换 key。

节点层保证：池已空时，不要按「query 条数」再打一排必然失败的 AnySearch。采集结果退化为博查 + 知识库（知识库开关关闭时只剩博查）。终评节点不感知图被改道，只看到 briefs 变少，以及一条不带 URL 的 discarded 说明。

这是节点内降级，不是 LangGraph 条件边，也不是再做一次换 key。

---

## 1. 现状

`config/flows/huayuan_radar_event_agent/flow.yaml`：

- `query_planner`（agent，工具含 `bocha_web_search`、`anysearch_web_search`）
- `evidence_gather`（函数节点 `radar_evidence_gather_func`）
- `score_summarizer`（agent，工具只有 `load_news_document`）
- 三条边的 condition 都是 `always`

`EvidenceGatherNode.execute()` 对每条规划 query 并行挂上博查和 AnySearch；知识库开关打开时再并列挂 Milvus 召回。单次失败写入 `discarded`，一条失败一行。`asyncio.gather(..., return_exceptions=True)` 保证一条工具异常不会取消其它源。

`_maybe_extract()` 对摘要短于 80 字的非知识库 brief 调用 `anysearch_extract`。知识库条目不走这条抽取。

终评提示词 `prompts/radar_event_score.md` 读取 `evidence_briefs` 与 `discarded_briefs`，并禁止编造 URL。图在 AnySearch 失败时本来就会走到终评；缺的是「池已空就不要扇出」和「相同熔断原因收成一条 discarded」。

`query_planner` 不在本方案改路由。它调用的仍是同一套工具，因此会提前消耗并熔断 key。采集节点开始时读的是同一份进程内池。

---

## 2. 为什么不改图

博查、AnySearch、知识库在同一个函数节点里并行。要表达「AnySearch 挂了走另一条边」，得把三路拆成三个图节点，再加条件边。终评的输入仍是 briefs，拆开只多一次状态往返。

`GraphBuilder` 已支持条件边。本需求用不到。`flow.yaml` 不改。

---

## 3. 依赖的工具层契约

节点不解析 HTTP 状态，不读取 key。只使用 260924-01 提供的两样东西：

1. `has_live_key() -> bool`：扇出前、抽取前各问一次。
2. 失败 JSON 的 `error_code == "anysearch_keys_exhausted"`。

其它 `error_code`（超时、400、429、502）仍按「这一条 query / 这一条 URL 失败」处理，不触发整路跳过。429 在工具层不熔断 key，节点也不把限流当成池耗尽。

---

## 4. 搜索扇出

在 `execute()` 组装 `coros` 之前询问池：

**没有存活 key**

- 不为任何 query 创建 `anysearch_web_search` 任务。
- `discarded` 先写入一条：`url` 为空，`reason` 为「AnySearch 凭证池无可用 key，本次跳过联网检索」。
- 博查任务、知识库任务与现在相同。

**仍有存活 key**

- 保持「每条 query × 博查 + AnySearch」的并行扇出。
- 工具层在单次调用内换 key。节点不重试。

并行过程中池被打空时，已经发出的 AnySearch 调用由工具返回 `anysearch_keys_exhausted`。合并 web 结果时：

- 该 `error_code` 的多条失败收成 **一条** discarded（reason 写明跳过 AnySearch，不拼接每条 query）。
- 其它 AnySearch 错误仍按 `tool_name@query` 各记一条，与现在相同。
- 博查失败仍各记一条。

这样终评上下文里不会出现 N 行相同的「凭证不可用」。

---

## 5. 抽取

`_maybe_extract()` 开头再问一次 `has_live_key()`。

池已空：不调用 `anysearch_extract`。若本会抽取的候选非空，`discarded` 追加一条「AnySearch 凭证池无可用 key，跳过页面抽取」。已有的搜索摘要保留在 briefs 里，不因为抽不了正文而丢掉。

池仍有 key：保持现在的 Top-N 短摘要抽取。单次抽取的换 key 由工具层完成。某条 URL 返回 `anysearch_keys_exhausted` 时，本批剩余 URL 不再继续打 extract（同一 `gather` 内后续任务直接记入那一条跳过原因）。

知识库 brief 继续排除在 AnySearch 抽取之外，改由终评按需调用 `load_news_document`。

---

## 6. 写回终评的数据

写回字段不变：

- `prompt_vars.evidence_briefs`
- `prompt_vars.discarded_briefs`
- `edges_var.brief_count` / `discarded_count` / 已有的 knowledge 计数

跳过记录的 `url` 必须为空，避免终评把它当成可引用链接。`radar_event_score.md` 已要求只使用 briefs 与 discarded 中出现的链接，且禁止编造 URL。本方案不改终评提示词。

不新增图状态字段，不把 key 或熔断集放进 `FlowState`。

---

## 7. 改动文件

| 文件 | 改动 |
|---|---|
| `backend/domain/flows/implementations/radar_evidence_gather_node.py` | 扇出前判断、熔断失败合并、抽取前判断 |
| `cursor_test/test_evidence_gather_anysearch_degrade.py` | 见第 8 节 |

依赖 260924-01 的 `has_live_key()` 与 `error_code`。工具层未落地时，节点改造不单独合并。

不改 `flow.yaml`、不改 `score_summarizer`、不改 `query_planner` 提示词。

---

## 8. 测试

`cursor_test/test_evidence_gather_anysearch_degrade.py`。池和两个搜索工具用 mock，不打外网。

- 池无存活 key、两条 query：AnySearch 调用次数为 0；博查仍按 query 调用；`discarded` 里 AnySearch 跳过原因只有一条；返回状态仍含 `evidence_briefs`（来自博查 mock）。
- 池有存活 key：AnySearch 仍按 query 扇出。
- 扇出结果里多条 `anysearch_keys_exhausted`：合并后 discarded 只有一条该原因。
- 一条 AnySearch 超时、另一条成功：超时仍单独占一行 discarded，成功结果进入 briefs。
- 池在抽取前变为空：`anysearch_extract` 调用次数为 0，已有 brief 仍写回。
- 知识库开关关闭时，降级路径不访问 Milvus。

---

## 9. 行为对照

| 场景 | 工具层 | 采集节点 | 终评 |
|---|---|---|---|
| 第一把 key 402，第二把成功 | 同一次调用换 key | 无感知，当作普通成功 | briefs 含 AnySearch |
| 调用过程中池被打空 | 返回 `anysearch_keys_exhausted` | 同类失败收成一条 discarded | 其余源的 briefs 仍在 |
| 进入采集时池已空 | 不被调用 | 不扇出 AnySearch | 只有博查 / 知识库 |
| 429 限流 | 不熔断、不换 key | 该条 query 单独 discarded | 其它 query 的 AnySearch 仍可成功 |
| 博查也失败 | 不涉及 | 博查各条记 discarded | briefs 可能为空，图仍走到终评 |
