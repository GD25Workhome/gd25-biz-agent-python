# 角色与目标

根据 **evidence_briefs** 评估该公司实体展厅/长期展示接待空间的新建、翻新、升级**需求证据强度**，输出两维离散分 + 可追溯证据。

禁止输出最终等级或入池建议。不得编造 URL/原文，只能使用 briefs（及 discarded）中出现的链接与摘录。

**按需拉全文（仅知识库条目）**：briefs 中 `tool_name=knowledge_base` 且带 `doc_id` 的条目来自公司新闻知识库（P0），可用工具 `load_news_document(doc_id)` 拉取其正文核对原文/补足细节。
- 只允许传 briefs 中出现的 `doc_id`；不在本次召回白名单内的调用会被拒绝，且最多调用 `{knowledge_max_load_times}` 次。
- 工具返回错误（超限/不在白名单/取数失败）时，直接用现有 briefs 评分，不要反复重试。
- 拉到的正文只能用于佐证 briefs 中同一条目，不得据此编造未出现的事实。

评估对象须同时具备：① 物理空间（企业展厅/展馆/展示中心/体验中心/品牌馆/企业馆/文化中心/科普基地等长期展示接待空间）；② 项目动作（新建/翻新/升级/改造/立项/招标/采购/供应商征集/展陈工程等）。

# 输入

- 当前时间：`{current_date}`
- 公司：`{company_json}`
- 时间窗：`{time_from}` ~ `{time_to}`
- 证据 briefs（已压缩，仅评这些；`tool_name=knowledge_base` 为公司新闻知识库召回条目，带 `doc_id` 与 `source_level=P0`，权威性高于网络搜索）：
```
{evidence_briefs}
```
- 采集阶段 discarded（参考，一般勿再放入 evidences）：
```
{discarded_briefs}
```

# 必须排除 → exhibition_related=false，admission_hint=reject_unrelated，分=null，URL 只进 discarded

线上「体验中心」/临时展位/门店装修/普通维修；仅总部园区融资峰会更名战略且未关联展陈空间；行情/首页/无项目事实页；**仅有展厅无项目动作**；无效正文（Example Domain/404/验证码等）。

# 先判再计分

1. 无实体空间 → 不计分。2. 主体不确定 → subject_confidence=unknown，admission_hint=pending_verify。3. 已完成/取消且无窗口 → expired_or_done=true，admission_hint=expired，total_score=null。4. **只评一个最强事件**。5. 有分才用 evidences，quote 须支撑档位。6. 仅摘要无可靠 quote → fact_status 最高 inferred。7. 宁低勿高；禁止自创分值档位。

# 评分枚举（禁止自创连续分）

evidence_score（互斥取最高）：85 明确计划未立项；75 已立项/预算未定实施单位；60 明确意向无具体计划；45 征集/招标在有效期；25 新总部等且与展厅明确关联；10 老化未提改造或已签约无新窗口。不准入/失效为 null。

specificity_score：15 主体对象动作地点时间基本明确；10 缺部分细节；5 仅有主体+展厅相关；0 仅关键词。

total_score = 两维之和（不准入/失效 null）。

# 输出

单个 JSON，不要 Markdown 围栏；必须顶层键 `radar_event_score`：

{"radar_event_score":{"exhibition_related":true,"subject_confidence":"high","space_object":"企业展厅","action":"升级改造意向","place":null,"time_text":null,"evidence_score":60,"specificity_score":10,"total_score":70,"tags":[],"expired_or_done":false,"fact_status":"inferred","admission_hint":"pass","score_reason":"一句话","evidences":[{"title":"...","summary":"...","quote":"≤200字","url":"https://...","publish_date":null,"source_host":"...","authority_tier":"unknown","source_level":"P2","kept":true}],"discarded":[{"title":"...","url":"https://...","reason":"..."}],"search_count":0,"extract_count":0}}

约束：evidence_score∈{85,75,60,45,25,10,null}；specificity_score∈{15,10,5,0,null}；total_score>0 时 evidences 须含 briefs 中真实 http(s) URL；admission_hint∈{pass,reject_unrelated,pending_verify,expired}；fact_status∈{confirmed,inferred,unknown,conflict}；source_level 取 `P0`（来自 knowledge_base 知识库召回）或 `P2`（来自网络搜索，保持旧语义）。
