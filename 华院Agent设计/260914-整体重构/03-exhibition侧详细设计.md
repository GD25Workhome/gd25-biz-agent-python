# news-url-crawl — exhibition 侧（Java）详细设计

> 项目：`/Users/shuxiaolong/work/unidt/exhibition`（yudao Spring Boot 多模块）
> 模块：`yudao-module-radar`
> 日期：2026-09-14（v2：本侧承担异步与落库）
> 上游：`01-总体设计.md`；服务端契约见 `02-gd25侧详细设计.md`

---

## 1. 本侧要做六件事

```text
① 提供「新闻列表入口页 URL」的来源           → §2
② 取上次已抓的详情页 URL list（known_urls）   → §3
③ 调 gd25 的 Agent 接口（同步，2~4 分钟）      → §4
④ 异步化：别让 Web 请求干等                   → §5
⑤ 拿到结果后落库（url_norm 去重）             → §6
⑥ 失败与超时处理                             → §7
```

**v2 的核心变化**：gd25 不再是异步任务系统，而是一个**跑完就返回的同步接口**。因此**异步、超时、状态、重试全部归本侧**。

这不是负担转移 —— 「给哪个企业抓、抓了几次、成没成」本身就是业务数据，放本侧天然合理（运维台可直接查）。

---

## 2. 新闻列表入口页 URL 从哪来（前置问题）

### 2.1 现状：不存在这个字段

`RadarCompanyDO`（`radar_company` 表）**没有任何新闻相关 URL 字段**。最接近的是：

```java
/** 官网域名 */
private String websiteDomain;
```

`websiteDomain` 是**域名**（`xinlong-holding.com`），不是**入口页**（`https://www.xinlong-holding.com/news.php?catid=93`）。触发抓取必须知道具体入口页。

### 2.2 方案：给 `radar_company` 加 `news_url`

```sql
ALTER TABLE radar_company
  ADD COLUMN news_url varchar(1024) NULL DEFAULT NULL
  COMMENT '新闻列表页 URL（Agent 抓取入口）' AFTER website_domain;
```

```java
// RadarCompanyDO.java —— 紧邻 websiteDomain
/** 官网域名 */
private String websiteDomain;

/** 新闻列表页 URL（Agent 抓取入口） */
private String newsUrl;
```

同步更新 `RadarCompanySaveReqVO` / `RadarCompanyRespVO`。

> **为什么放 `radar_company` 而不是新建表**：一个企业一个新闻入口，是 1:1 属性；运维台按企业维度操作，放主表最顺手。

### 2.3 入口 URL 的录入

本次**不解决**「如何自动发现企业的新闻列表页」。V1 人工录入（运维台/导入脚本）。

⚠️ `news_url` 为空时触发应返回明确错误，**不要**退化到用 `website_domain` 猜。

---

## 3. `known_urls` 从哪来

需求原文：「提交时给到其最近的10条新闻地址」。

**来源就是本侧已落库的新闻 URL** —— 取该企业最近入库的 N 条（默认 10）：

```sql
SELECT news_url
FROM radar_company_news_url
WHERE company_id = #{companyId} AND deleted = b'0'
ORDER BY create_time DESC
LIMIT #{limit};
```

**两点说明**：

1. **为什么不查"含正文的"**：本能力只采列表入口 URL，落库的也都是 URL，直接用即可。
2. **首次抓取 `known_urls=[]`**：Agent 会全量翻页（成本最高的一次）。这符合预期，运维台可提示「首次抓取成本较高」。

> ⚠️ 需求说「最近的 10 条」，但**建议传更多**（如 50~100）。理由：站点每页约 20~30 条，只传 10 条时 Agent 翻到第 2 页就可能「全部不命中」，误以为还有新内容而继续翻页。传 50 条能让「已翻到历史区域」的信号更明确，**直接省钱**。见 §8 遗留决策。

---

## 4. 调用 gd25（复用 `RadarAgentClient`）

### 4.1 复用既有客户端，不新建

`RadarAgentClient`（`framework/agent/client/RadarAgentClient.java`）已是标准的 FastAPI 客户端，**只加方法**。遵守它已有约定：

- hutool `HttpRequest` + try-with-resources `HttpResponse`
- `enabled` 开关 + `xxxMock` 离线开关
- 每接口独立超时属性
- 错误信息 `StrUtil.maxLength(respBody, 300)` 截断
- `ServiceException` 原样抛出，其它包装 `AGENT_CALL_FAILED`

### 4.2 新增配置

`RadarAgentProperties` 加：

```java
/** 新闻 URL 抓取接口路径 */
private String newsUrlCrawlPath = "/api/v1/huayuan/news-url-crawl";
/** 新闻 URL 抓取超时（毫秒）。Agent 实测 2~4 分钟，须大于 gd25 侧 600s */
private Long newsUrlCrawlTimeoutMs = 620_000L;
/** mock 开关（离线联调） */
private Boolean newsUrlCrawlMock = false;

public String buildNewsUrlCrawlUrl() {
    return joinUrl(baseUrl, newsUrlCrawlPath);
}
```

`application-local.yaml`：

```yaml
radar:
  agent:
    news-url-crawl-path: /api/v1/huayuan/news-url-crawl
    news-url-crawl-timeout-ms: 620000     # ⚠️ 不是 30s：这是同步长接口
    news-url-crawl-mock: false
```

> ⚠️ **超时必须是 620s**：gd25 侧墙钟超时 600s，客户端须略大。这与既有 `radar-event-score-timeout-ms: 1200000` 是同类设计。

### 4.3 客户端方法

```java
/**
 * 调用 gd25 的新闻 URL 抓取接口（同步，2~4 分钟）。
 *
 * @param requestBody {news_list_url, known_urls, company_name, stock_code, max_pages}
 * @return {news_urls, list_pages_fetched, stop_reason, stats, trace_id}
 */
public JSONObject crawlNewsUrls(JSONObject requestBody) {
    if (Boolean.FALSE.equals(agentProperties.getEnabled())) {
        throw exception(AGENT_CALL_FAILED, "radar.agent.enabled=false");
    }
    if (Boolean.TRUE.equals(agentProperties.getNewsUrlCrawlMock())) {
        return buildMockNewsUrlCrawl(requestBody);
    }
    String url = agentProperties.buildNewsUrlCrawlUrl();
    String body = requestBody == null ? "{}" : requestBody.toString();
    int timeout = Math.max(
            agentProperties.getConnectTimeoutMs(),
            agentProperties.getNewsUrlCrawlTimeoutMs() == null
                    ? 620_000 : agentProperties.getNewsUrlCrawlTimeoutMs().intValue());
    log.info("[RadarAgentClient] crawlNewsUrls POST {} known={}",
            url, requestBody == null ? 0 : CollectionUtil.size(requestBody.getJSONArray("known_urls")));
    try (HttpResponse response = HttpRequest.post(url)
            .header("Content-Type", "application/json")
            .body(body)
            .timeout(timeout)
            .execute()) {
        String respBody = response.body();
        if (!response.isOk()) {
            throw exception(AGENT_CALL_FAILED,
                    "HTTP " + response.getStatus() + ", body=" + StrUtil.maxLength(respBody, 300));
        }
        if (StrUtil.isBlank(respBody)) {
            throw exception(AGENT_RESPONSE_EMPTY);
        }
        return JSONUtil.parseObj(respBody);
    } catch (ServiceException ex) {
        throw ex;
    } catch (Exception ex) {
        log.error("[RadarAgentClient] crawlNewsUrls 调用失败 url={}", url, ex);
        throw exception(AGENT_CALL_FAILED, ex.getMessage());
    }
}
```

### 4.4 curl 调用案例（联调 gd25）

本地 gd25 默认 `http://127.0.0.1:8000`。接口同步执行约 2~4 分钟，**curl 超时须 ≥620s**（与 `news-url-crawl-timeout-ms` 一致）。

**首次抓取**（`known_urls` 为空，全量翻页）：

```bash
curl -sS -X POST 'http://127.0.0.1:8000/api/v1/huayuan/news-url-crawl' \
  -H 'Content-Type: application/json' \
  --max-time 620 \
  -d '{
    "news_list_url": "https://www.xinlong-holding.com/news.php?catid=93",
    "known_urls": [],
    "company_name": "新龙控股",
    "stock_code": "000955",
    "max_pages": 8,
    "trace_id": "exhibition-local-001"
  }'
```

**增量抓取**（带上次已落库的详情 URL，命中后 Agent 应 `stop_reason=hit_known`）：

```bash
curl -sS -X POST 'http://127.0.0.1:8000/api/v1/huayuan/news-url-crawl' \
  -H 'Content-Type: application/json' \
  --max-time 620 \
  -d '{
    "news_list_url": "https://www.xinlong-holding.com/news.php?catid=93",
    "known_urls": [
      "https://www.xinlong-holding.com/shownews.php?id=1234",
      "https://www.xinlong-holding.com/shownews.php?id=1233"
    ],
    "company_name": "新龙控股",
    "stock_code": "000955",
    "max_pages": 8,
    "trace_id": "exhibition-local-002"
  }'
```

成功响应示例（字段契约与 `02-gd25侧详细设计.md` §3.2 一致；`news_urls` 已减去 `known_urls`）：

```json
{
  "news_urls": [
    {
      "url": "https://www.xinlong-holding.com/shownews.php?id=1300",
      "title": "示例新闻标题",
      "published_at": "2026-09-10"
    }
  ],
  "list_pages_fetched": 2,
  "stop_reason": "hit_known",
  "stats": {
    "candidate_count": 45,
    "known_hit_count": 2,
    "list_page_urls": [
      "https://www.xinlong-holding.com/news.php?catid=93",
      "https://www.xinlong-holding.com/news.php?catid=93&page=2"
    ],
    "agent_turns": 12,
    "agent_cost_usd": 0.08,
    "duration_ms": 185000
  },
  "trace_id": "exhibition-local-002"
}
```

| HTTP | 含义 | 本侧应对 |
|---|---|---|
| 200 | 成功；若 `stop_reason=no_detail_links` 仍是 200，表示通道抽链失败 | 记 `NEWS_CRAWL_CHANNEL_BLOCKED`，勿当成功落库 |
| 503 | gd25 未启用（`NEWS_CRAWL_ENABLED=false` 或无凭证） | 配置/运维问题 |
| 504 | Agent 超过 gd25 墙钟超时（默认 600s） | 映射 `NEWS_CRAWL_TIMEOUT` |
| 502 | 列表页抓取失败 / Agent 执行失败 | 映射 `NEWS_CRAWL_AGENT_FAILED` |

> 前提：gd25 `.env` 中 `NEWS_CRAWL_ENABLED=true`，已配 Anthropic 凭证，且宿主机有可用 `claude` CLI。否则会直接 503 或 502。

### 4.5 错误码

`ErrorCodeConstants` 增加（段位请顺延，避免冲突）：

```java
// ========== 新闻 URL 抓取 1_021_xxx ==========
ErrorCode NEWS_CRAWL_COMPANY_NO_URL  = new ErrorCode(1_021_001_000, "企业未配置新闻列表页 URL");
ErrorCode NEWS_CRAWL_AGENT_FAILED    = new ErrorCode(1_021_001_001, "新闻抓取失败：{}");
ErrorCode NEWS_CRAWL_TIMEOUT         = new ErrorCode(1_021_001_002, "新闻抓取超时（Agent 侧未在 600s 内完成）");
ErrorCode NEWS_CRAWL_CHANNEL_BLOCKED = new ErrorCode(1_021_001_003, "目标站点无法抽取新闻链接（可能需 JS 渲染）");
```

---

## 5. 异步化（本侧的核心）

### 5.1 场景判断

| 触发场景 | 方案 |
|---|---|
| **运维台点按钮** | `@Async` 后台跑 + 前端轮询本侧状态 |
| **定时任务批量跑** | Quartz Job 顺序/并发跑，无需前端 |
| 两者都有 | 统一走 Service + 状态表，两种入口都调它 |

### 5.2 状态落哪里

**不建独立任务表**，在 `radar_company` 上加三列 —— 一个企业同时只应有一次抓取，1:1 属性：

```sql
ALTER TABLE radar_company
  ADD COLUMN news_crawl_status varchar(32) NULL DEFAULT NULL
  COMMENT '新闻抓取状态：RUNNING/SUCCESS/FAILED，NULL 表示从未抓取',
  ADD COLUMN news_crawl_time datetime NULL DEFAULT NULL
  COMMENT '最后一次抓取时间',
  ADD COLUMN news_crawl_error varchar(1000) NULL DEFAULT NULL
  COMMENT '最后一次抓取失败原因',
  ADD COLUMN news_crawl_total int NULL DEFAULT NULL
  COMMENT '最后一次抓取的候选总数';
```

**为什么不用独立任务表**：需求没有「任务历史」诉求；一个企业一条状态足够运维台展示。若日后要历史，再加 `radar_company_news_crawl_log` 表（见 §8 遗留决策）。

### 5.3 Service 接口

```java
public interface RadarNewsCrawlService {

    /**
     * 触发一次新闻 URL 抓取（异步，立即返回）。
     *
     * 内部用 @Async 执行真正抓取，状态写 radar_company.news_crawl_status。
     *
     * @param companyId 企业 ID
     */
    void triggerCrawlAsync(Long companyId);

    /**
     * 同步执行一次抓取（供 Quartz Job 或内部调用）。
     *
     * @param companyId 企业 ID
     * @return 抓取结果
     */
    RadarNewsCrawlResultVO crawlSync(Long companyId);
}
```

### 5.4 实现

```java
@Service
@Validated
public class RadarNewsCrawlServiceImpl implements RadarNewsCrawlService {

    private static final int KNOWN_URLS_LIMIT = 50;
    private static final String STATUS_RUNNING = "RUNNING";
    private static final String STATUS_SUCCESS = "SUCCESS";
    private static final String STATUS_FAILED = "FAILED";

    @Resource
    private RadarCompanyMapper companyMapper;
    @Resource
    private RadarCompanyNewsUrlMapper newsUrlMapper;
    @Resource
    private RadarAgentClient agentClient;
    @Resource
    private RadarAsyncTaskRunner asyncTaskRunner;   // 复用既有 JVM 内队列

    @Override
    public void triggerCrawlAsync(Long companyId) {
        RadarCompanyDO company = companyMapper.selectById(companyId);
        if (company == null) {
            throw exception(NEWS_CRAWL_AGENT_FAILED, "企业不存在");
        }
        if (StrUtil.isBlank(company.getNewsUrl())) {
            throw exception(NEWS_CRAWL_COMPANY_NO_URL);
        }
        if (STATUS_RUNNING.equals(company.getNewsCrawlStatus())) {
            throw exception(NEWS_CRAWL_AGENT_FAILED, "该企业正在抓取中");
        }
        // 置 RUNNING（独立事务，立即可见，供前端轮询）
        markStatus(companyId, STATUS_RUNNING, null, null);
        // 复用既有 JVM 内异步队列（RadarAsyncTaskType 需新增 NEWS_CRAWL）
        asyncTaskRunner.enqueue(RadarAsyncTaskType.NEWS_CRAWL, companyId,
                RadarEnqueuePriority.NORMAL);
    }

    @Override
    public RadarNewsCrawlResultVO crawlSync(Long companyId) {
        RadarCompanyDO company = companyMapper.selectById(companyId);
        if (company == null || StrUtil.isBlank(company.getNewsUrl())) {
            throw exception(NEWS_CRAWL_COMPANY_NO_URL);
        }
        try {
            List<String> knownUrls = newsUrlMapper.selectRecentUrls(companyId, KNOWN_URLS_LIMIT);

            JSONObject body = new JSONObject();
            body.set("news_list_url", company.getNewsUrl());
            body.set("known_urls", knownUrls);
            body.set("company_name", company.getName());
            body.set("stock_code", company.getStockCode());

            JSONObject resp = agentClient.crawlNewsUrls(body);
            return handleResponse(companyId, resp);
        } catch (ServiceException ex) {
            markStatus(companyId, STATUS_FAILED, ex.getMessage(), null);
            throw ex;
        } catch (Exception ex) {
            markStatus(companyId, STATUS_FAILED, StrUtil.maxLength(ex.getMessage(), 990), null);
            log.error("[RadarNewsCrawl] 抓取异常 companyId={}", companyId, ex);
            throw exception(NEWS_CRAWL_AGENT_FAILED, ex.getMessage());
        }
    }
}
```

**`handleResponse` —— 按 `stop_reason` 分流**：

```java
private RadarNewsCrawlResultVO handleResponse(Long companyId, JSONObject resp) {
    String stopReason = resp.getStr("stop_reason", "no_next");
    JSONArray urls = resp.getJSONArray("news_urls");
    int candidateTotal = resp.getJSONObject("stats") == null
            ? 0 : resp.getJSONObject("stats").getInt("candidate_count", 0);

    // ⚠️ 通道问题：执行成功但零链接 —— 落库为空但状态记 FAILED，触发告警
    if ("no_detail_links".equals(stopReason)) {
        markStatus(companyId, STATUS_FAILED, "站点无法抽取新闻链接（可能需 JS 渲染）", candidateTotal);
        throw exception(NEWS_CRAWL_CHANNEL_BLOCKED);
    }

    int inserted = persistNewsUrls(companyId, urls);
    markStatus(companyId, STATUS_SUCCESS, null, candidateTotal);

    RadarNewsCrawlResultVO vo = new RadarNewsCrawlResultVO();
    vo.setStopReason(stopReason);
    vo.setListPagesFetched(resp.getInt("list_pages_fetched", 0));
    vo.setTotalCount(urls == null ? 0 : urls.size());
    vo.setInsertedCount(inserted);
    log.info("[RadarNewsCrawl] 完成 companyId={} stop={} total={} inserted={}",
            companyId, stopReason, vo.getTotalCount(), inserted);
    return vo;
}
```

> **`no_detail_links` 记 FAILED 而非 SUCCESS**：虽然服务端返回 200，但业务上「一条都没抓到」是需要人工介入的故障（通道问题）。在本侧记 FAILED 才能在运维台看见。这**不是**把 200 当错误，而是业务语义判定。

---

## 6. 结果落库：`radar_company_news_url`

### 6.1 建表

```sql
CREATE TABLE radar_company_news_url (
  `id`            bigint        NOT NULL AUTO_INCREMENT COMMENT '主键',
  `company_id`    bigint        NOT NULL COMMENT '企业 ID（首次发现该 URL 的企业）',
  `news_url`      varchar(1024) NOT NULL COMMENT '新闻详情 URL',
  `url_norm`      varchar(512)  NOT NULL COMMENT '规范化 URL（全局去重键）',
  `url_hash`      char(40)      NOT NULL COMMENT 'url_norm 的 sha1，用于唯一索引',
  `title`         varchar(512)  NULL DEFAULT NULL COMMENT '标题',
  `published_at`  varchar(32)   NULL DEFAULT NULL COMMENT '发布日期（原文表述）',
  `source`        varchar(32)   NOT NULL DEFAULT 'agent' COMMENT '来源：agent/rule/manual',
  `creator`       varchar(64)   NULL DEFAULT '',
  `create_time`   datetime      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updater`       varchar(64)   NULL DEFAULT '',
  `update_time`   datetime      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted`       bit(1)        NOT NULL DEFAULT b'0',
  `tenant_id`     bigint        NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  -- ⚠️ 全局唯一；用 url_hash 而非 url_norm，避免索引超长
  UNIQUE KEY `uk_news_url_hash` (`url_hash`, `deleted`),
  KEY `idx_company_time` (`company_id`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='企业新闻 URL（Agent 抓取结果）';
```

**两个设计点**：

1. **`url_hash` 而不是直接索引 `url_norm`**：InnoDB 单列索引前缀上限 3072 字节；`url_norm` 是 `varchar(512)` utf8mb4 = 2048 字节，**贴边**。`char(40)` 的 sha1 更稳。
2. **唯一键带 `deleted`** 是 yudao 惯例（逻辑删除下允许「删了再插」）。

### 6.2 DO

```java
@TableName("radar_company_news_url")
@KeySequence("radar_company_news_url_seq")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class RadarCompanyNewsUrlDO extends BaseDO {

    @TableId
    private Long id;

    /** 企业 ID */
    private Long companyId;

    /** 新闻详情 URL */
    private String newsUrl;

    /** 规范化 URL（全局去重键） */
    private String urlNorm;

    /** url_norm 的 sha1，用于唯一索引 */
    private String urlHash;

    /** 标题 */
    private String title;

    /** 发布日期（原文表述） */
    private String publishedAt;

    /** 来源：agent/rule/manual */
    private String source;
}
```

### 6.3 落库（L3 去重）

```java
private int persistNewsUrls(Long companyId, JSONArray urls) {
    if (urls == null || urls.isEmpty()) {
        return 0;
    }
    List<RadarCompanyNewsUrlDO> batch = new ArrayList<>(urls.size());
    for (int i = 0; i < urls.size(); i++) {
        JSONObject item = urls.getJSONObject(i);
        String url = StrUtil.trim(item.getStr("url"));
        if (StrUtil.isBlank(url)) {
            continue;
        }
        String norm = RadarUrlNormUtil.normalize(url);
        batch.add(RadarCompanyNewsUrlDO.builder()
                .companyId(companyId)
                .newsUrl(url)
                .urlNorm(norm)
                .urlHash(DigestUtil.sha1Hex(norm))
                .title(StrUtil.maxLength(item.getStr("title"), 500))
                .publishedAt(item.getStr("published_at"))
                .source("agent")
                .build());
    }
    if (batch.isEmpty()) {
        return 0;
    }
    // 靠 uk_news_url_hash 做最终去重；重复行忽略
    return newsUrlMapper.insertBatchIgnoreDuplicate(batch);
}
```

Mapper（MySQL `INSERT IGNORE`）：

```java
/**
 * 批量插入，命中唯一键的整行忽略，返回实际插入行数。
 */
@Insert("<script>"
        + "INSERT IGNORE INTO radar_company_news_url "
        + "(company_id, news_url, url_norm, url_hash, title, published_at, source, "
        + " creator, create_time, updater, update_time, deleted, tenant_id) VALUES "
        + "<foreach collection='list' item='it' separator=','>"
        + "(#{it.companyId}, #{it.newsUrl}, #{it.urlNorm}, #{it.urlHash}, #{it.title}, "
        + "#{it.publishedAt}, #{it.source}, #{it.creator}, NOW(), #{it.updater}, "
        + "NOW(), b'0', #{it.tenantId})"
        + "</foreach>"
        + "</script>")
int insertBatchIgnoreDuplicate(@Param("list") List<RadarCompanyNewsUrlDO> list);
```

**三层去重的落点**（对应 `01` §5.3）：L1/L2 在 gd25 的 Agent 内，**L3 就是这里** —— 靠唯一索引做最终保证。即使服务端返回了重复、或同一 URL 被两个企业先后发现，这里也只有一条。

### 6.4 `RadarUrlNormUtil`（必须与 gd25 一致）

> ⚠️ **本设计最容易出静默错误的地方。** 两侧 `url_norm` 规则**必须逐字一致**，否则：
> - gd25 的 L1 短路会失准（本侧传的 `known_urls` 服务端认不出）
> - 去重会出现「同一 URL 存两条」

```java
/**
 * 新闻 URL 规范化 —— 规则必须与 gd25 侧
 * backend/domain/news_crawl/url_norm.py 完全一致。
 *
 * 规则：
 *  1. 仅保留 host + path + query（去 scheme、去 fragment）
 *  2. host 小写
 *  3. 仅当【没有 query】时才去 path 尾斜杠
 *     ⚠️ 若 path 尾斜杠 + 有 query，该斜杠是语义的一部分：
 *        去掉会把 `/news/html/?109.html` 变成 `/news/html?109.html`
 *        （gd25 实验中出现过的真实 bug，导致 24 条 URL 误判）
 *  4. query 参数按键名排序，保证 `?a=1&b=2` 与 `?b=2&a=1` 归一
 */
public static String normalize(String rawUrl) {
    if (StrUtil.isBlank(rawUrl)) {
        return "";
    }
    try {
        URL url = new URL(rawUrl.trim());
        String host = url.getHost().toLowerCase();
        String path = StrUtil.blankToDefault(url.getPath(), "/");
        String query = url.getQuery();

        if (StrUtil.isBlank(query) && path.length() > 1 && path.endsWith("/")) {
            path = path.substring(0, path.length() - 1);
        }
        String normQuery = normalizeQuery(query);
        return host + path + (StrUtil.isBlank(normQuery) ? "" : "?" + normQuery);
    } catch (Exception ex) {
        log.warn("[RadarUrlNormUtil] URL 解析失败，回退原文 rawUrl={}", rawUrl, ex);
        return rawUrl.trim();
    }
}

/**
 * query 参数按键名排序后重组。
 */
private static String normalizeQuery(String query) {
    if (StrUtil.isBlank(query)) {
        return "";
    }
    List<String> pairs = StrUtil.split(query, '&');
    pairs.sort(Comparator.naturalOrder());
    return StrUtil.join("&", pairs);
}
```

**必须对齐的两条**（`02` §5.1）：
1. 仅当无 query 时才去尾斜杠
2. query 参数排序

**建议加跨语言一致性测试**，覆盖：
- `/news/html/?109.html`（尾斜杠 + query）
- `?b=2&a=1` vs `?a=1&b=2`（参数顺序）
- `http://` vs `https://`（应归一）
- 带 `#fragment`

---

## 7. 失败与超时

| 情况 | gd25 返回 | 本侧处理 |
|---|---|---|
| 正常 | 200 | 落库，记 SUCCESS |
| 参数非法 | 422 | 记 FAILED（通常是本侧 bug，需修） |
| Agent 超时 | **504** | 记 FAILED，**不自动重试**（重试=重跑一次=$0.73） |
| 列表页抓取失败 | **502** | 记 FAILED |
| 站点需 JS 渲染 | 200 + `no_detail_links` | 记 FAILED + 告警（业务判定，见 §5.4） |
| 网络异常/连接超时 | — | 记 FAILED |

### 7.1 不自动重试的理由

重试 = 重跑一次 Agent = **$0.73**。且失败类型不同，重试价值不同：

| 失败类型 | 重试有用吗 |
|---|---|
| 504 超时 | 可能有（网络抖动） |
| 502 列表抓取失败 | 可能有（对方站点临时故障） |
| `no_detail_links` | **无用**（通道问题，站点结构使然） |

**建议**：不自动重试；由运维台人工判断后手动触发，或次日定时任务自然重跑。

### 7.2 并发控制

gd25 侧有信号量限制（默认 2）。若本侧的 Quartz Job 一次扫 50 个企业并发调，会大量排队。

**建议**：Job 内**串行**调用，或加限流：

```java
for (RadarCompanyDO company : pendingList) {
    try {
        newsCrawlService.crawlSync(company.getId());
    } catch (Exception ex) {
        log.warn("[RadarNewsCrawlJob] 抓取失败 companyId={}", company.getId(), ex);
    }
    // 串行 + 间隔，避免把 gd25 打满
    ThreadUtil.sleep(1000);
}
```

---

## 8. 运维台（建议做，但可延后）

| 位置 | 内容 |
|---|---|
| `RadarCompanyController` | `POST /radar/company/news-crawl/trigger?companyId=` 手动触发 |
| 运行台列 | 「新闻抓取」：`news_crawl_status` + `news_crawl_time` |
| 详情 | 已入库 URL 数 + 最近 10 条 |

权限串沿用既有风格：`radar:company:news-crawl`。

**前端轮询**：点触发后，按 10s 间隔轮询企业详情，直到 `news_crawl_status` 变为 `SUCCESS`/`FAILED`（最长约 5~10 分钟）。

---

## 9. 策略：日常热跑 vs 冷启动

`01` §7 提到「日常热跑可先走规则版」。落到本侧就是一个**分流策略**：

```text
定时任务（每日）
  ├─ 先跑规则版 company_news_crawl（零 LLM 成本）
  ├─ 规则版成功的站点 → 直接落库
  └─ 规则版失败/零产出的站点 → 调 gd25 Agent（$0.73）
```

**理由**：实验里 Agent 3/3 稳定的 5 个站，规则版在欣龙控股、峆一药业是**零增量**、英飞特零产出 —— 这些正是该调 Agent 的。而规则版能跑通的站点，没必要每次花 $0.73。

⚠️ 本设计**不含**这个分流调度（属另一条需求）。此处仅记录策略方向，避免直接用 Agent 做全量日跑导致成本失控。

---

## 10. 实施顺序

```text
J0  DDL：radar_company 加 5 列 + 新建 radar_company_news_url     ← 无依赖
J1  DO/Mapper + RadarUrlNormUtil + 跨语言一致性测试 ★            ← 关键正确性
J2  RadarAgentClient.crawlNewsUrls + 配置 + mock 分支            ← 可与 gd25 并行
J3  RadarNewsCrawlService（crawlSync / handleResponse / 落库）    ← 核心
J4  @Async / Job 触发 + 状态置位                                 ← 打通
J5  运维台（可选）
```

★ = 关键正确性项

**联调**：`news-url-crawl-mock: true` 可先跑通本侧全链路，不必等 gd25 就绪。

---

## 11. 与既有 radar 机制的关系

| 既有机制 | 是否复用 | 说明 |
|---|---|---|
| `RadarAgentClient` | ✅ **复用**（只加方法） | 不新建 HTTP 客户端 |
| `RadarAsyncTaskRunner` | ✅ **复用** | JVM 内异步队列，新增 `RadarAsyncTaskType.NEWS_CRAWL` |
| Quartz `JobHandler` | ✅ **复用** | 驱动定时/批量抓取 |
| `@TenantJob` | ✅ **复用** | 多租户逐租户执行 |
| `CommonResult<T>` | ✅ **复用** | 控制器返回值 |
| `BaseMapperX` / `LambdaQueryWrapperX` | ✅ **复用** | Mapper 写法 |
| `RadarCrawlTaskStatusEnum` | ⚠️ **不复用** | 那是 `radar_crawl_task`（巨潮采集，MySQL）的状态，与本次无关 |
| `radar_crawl_task` 表 | ❌ **不动** | 巨潮采集线，另属一条数据线 |
| `radar_raw_document` | ❌ **不写** | 结果落新专表；两处写会造成双源 |

**关键区分**：本设计**不建任务表**（用 `radar_company` 的 4 个状态列），**不碰** `radar_crawl_task`。

---

## 12. 遗留决策

| # | 问题 | 建议 |
|---|---|---|
| 1 | `known_urls` 传 10 条还是更多 | **建议 50**（§3），10 条会让短路信号失准 —— 但需求原文写 10，需确认 |
| 2 | `news_url` 录入方式 | V1 人工；自动发现另立需求 |
| 3 | 是否需要抓取历史表 | V1 不要；4 个状态列够用 |
| 4 | 是否做「规则版优先 + Agent 兜底」分流 | 建议做（§9），但不属本次范围 |
| 5 | `@Async` 还是 Quartz 驱动 | 点按钮场景用 `@Async`；批量用 Quartz |
| 6 | 存量企业 `news_url` 批量补 | 需运营提供清单 |
| 7 | 失败是否自动重试 | **不自动**（§7.1），人工判断 |
