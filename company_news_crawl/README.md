# company_news_crawl

A股上市公司官网新闻中心爬虫 MVP

## 功能简介

本包用于爬取 A 股上市公司官网新闻中心页面，将其转换为知识库友好的格式，服务于展厅发觉 Agent 等产品需求。

### 核心能力

- ✅ 加载公司种子列表（JSONL/JSON）
- ✅ HTTP 方式获取新闻列表页
- ✅ **结构化列表提取**：从列表页直接提取 URL、标题、发布日期（list-with-date 模式）
- ✅ **静态分页支持**：自动跟随"下一页"链接，可配置最大页数（默认 3 页）
- ✅ 基于启发式规则提取同域文章链接
- ✅ **增强的内容提取**：
  - 支持 h3/h5 标题和日期模式（适配平安银行等站点）
  - 自动过滤导航标题（如「组织架构」「关于我们」）
  - 列表页元数据作为回退（当详情页提取失败时）
- ✅ 提取文章标题、发布时间、正文内容
- ✅ 输出 JSONL 格式结果（含站点档案、文章记录、错误日志）
- ✅ 站点类型识别（static/cms/spa/api/blocked）
- ✅ MySQL schema 定义（供未来接入）

### 非目标（本 MVP 不含）

- ❌ Playwright 浏览器自动化（SPA 站点会标记跳过）
- ❌ LLM 驱动的链接提取
- ❌ 直接写入生产 MySQL 数据库
- ❌ 巨潮资讯等公告专项爬虫（见 `radar_crawl/`）

## 安装依赖

```bash
pip install -r requirements.txt
```

**核心依赖**:
- `httpx` - HTTP 客户端
- `selectolax` - 快速 HTML 解析
- `trafilatura` - 正文提取
- `python-dotenv` - 环境变量（可选）

## 快速开始

### 1. 基础用法

```bash
# 使用示例种子文件
python -m company_news_crawl once \
  --seed examples/seed_sample.json \
  --out /tmp/company_news_output.jsonl
```

### 2. 自定义参数

```bash
# 限制每家公司最多 10 篇文章
python -m company_news_crawl once \
  --seed my_companies.json \
  --out result.jsonl \
  --max-articles 10 \
  --timeout 15

# 启用分页（最多爬取 5 页）
python -m company_news_crawl once \
  --seed my_companies.json \
  --out result.jsonl \
  --max-pages 5
```

### 3. 使用环境变量

创建 `.env` 文件：

```bash
CRAWL_MAX_ARTICLES=30
CRAWL_TIMEOUT=20
CRAWL_REQUEST_INTERVAL=2.0
CRAWL_OUTPUT_DIR=/data/crawl
```

然后运行：

```bash
python -m company_news_crawl once --seed seed.json --out out.jsonl
```

## 输入格式

### 种子文件格式（JSON）

```json
[
  {
    "stock_code": "000001",
    "company_name": "平安银行",
    "news_list_url": "http://bank.pingan.com/bankPingAnCom/about/news"
  },
  {
    "stock_code": "000063",
    "company_name": "中兴通讯",
    "news_list_url": "https://www.zte.com.cn/china/about/news.html"
  }
]
```

### 种子文件格式（JSONL）

```jsonl
{"stock_code": "000001", "company_name": "平安银行", "news_list_url": "http://bank.pingan.com/..."}
{"stock_code": "000063", "company_name": "中兴通讯", "news_list_url": "https://www.zte.com.cn/..."}
```

## 输出格式

### 主输出文件（JSONL）

每行一条 JSON 记录，包含三种类型：

**1. 站点档案 (profile)**

```json
{
  "type": "profile",
  "data": {
    "stock_code": "000001",
    "company_name": "平安银行",
    "list_url": "http://bank.pingan.com/...",
    "site_type": "cms",
    "last_http_status": 200,
    "last_article_link_count": 15,
    "last_success_at": "2026-09-12T12:00:00",
    "fail_streak": 0,
    "notes": ""
  }
}
```

**2. 文章记录 (article)**

```json
{
  "type": "article",
  "data": {
    "stock_code": "000001",
    "company_name": "平安银行",
    "source_level": "P0_official_site",
    "list_url": "http://bank.pingan.com/...",
    "article_url": "http://bank.pingan.com/news/detail/123",
    "url_norm": "http://bank.pingan.com/news/detail/123",
    "title": "平安银行发布2026年度报告",
    "published_at": "2026-03-15",
    "fetched_at": "2026-09-12T12:05:30",
    "content_text": "正文内容...",
    "content_hash": "a1b2c3...",
    "summary": "前200字摘要...",
    "http_status": 200,
    "fetch_method": "http",
    "template_id": "generic",
    "site_type": "cms",
    "parse_version": "company_news_mvp_v1"
  }
}
```

**3. 错误日志 (errors)**

```json
{
  "type": "errors",
  "stock_code": "000001",
  "errors": [
    "Failed to extract content from http://..."
  ]
}
```

### 汇总文件（JSON）

自动生成 `*_summary.json`，示例：

```json
{
  "total_companies": 7,
  "successful_companies": 5,
  "total_articles": 87,
  "total_errors": 3,
  "companies": [
    {
      "stock_code": "000001",
      "company_name": "平安银行",
      "article_count": 15,
      "error_count": 0,
      "site_type": "cms"
    }
  ]
}
```

## 配置选项

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CRAWL_TIMEOUT` | 20 | HTTP 超时时间（秒） |
| `CRAWL_MAX_RETRIES` | 2 | 失败重试次数 |
| `CRAWL_REQUEST_INTERVAL` | 1.0 | 请求间隔（秒） |
| `CRAWL_MAX_ARTICLES` | 20 | 每家公司最大文章数 |
| `CRAWL_MAX_PAGES` | 3 | 每家公司最大爬取页数（分页） |
| `CRAWL_MAX_CONCURRENT` | 1 | 最大并发数（MVP 固定为 1） |
| `CRAWL_OUTPUT_DIR` | /tmp/company_news_crawl | 默认输出目录 |

### 代码配置

参见 `company_news_crawl/config.py` 中的 `CrawlConfig` 类。

## 项目结构

```
company_news_crawl/
├── README.md                 # 本文档
├── requirements.txt          # Python 依赖
├── __init__.py
├── __main__.py              # CLI 入口
├── config.py                # 配置管理
├── models.py                # 数据模型（SiteProfile, ArticleRecord, CrawlResult）
├── adapters/                # 适配器层
│   ├── http_client.py       # HTTP 客户端封装
│   ├── list_extractor.py    # 列表页链接提取
│   ├── content_extractor.py # 正文内容提取
│   └── site_profiler.py     # 站点类型识别
├── pipeline/                # 处理流水线
│   ├── crawl_one.py         # 单公司爬取逻辑
│   └── crawl_batch.py       # 批量爬取逻辑
├── db/                      # 数据持久化
│   ├── schema.sql           # MySQL DDL（未来使用）
│   ├── jsonl_sink.py        # JSONL 输出
│   └── repository.py        # 数据库接口（占位）
├── examples/                # 示例数据
│   └── seed_sample.json     # 示例种子文件（7家公司）
└── tests/                   # 测试（可选）
    ├── test_list_extractor.py
    └── fixtures/*.html
```

## 与 `radar_crawl` 的区别

| 维度 | `radar_crawl` (巨潮) | `company_news_crawl` (官网) |
|------|---------------------|----------------------------|
| **数据源** | 巨潮资讯网公告 | 公司官网新闻中心 |
| **来源级别** | P1/P2 公告 | P0 官网 |
| **数据结构** | PDF + 结构化字段 | HTML → 纯文本 |
| **任务队列** | MySQL task table | 暂无（MVP 单次运行） |
| **工作者模式** | 多 worker + 任务调度 | 单次批量/顺序 |
| **输出** | 数据库 + PDF 存储 | JSONL 文件（可选数据库） |

两者为**互补关系**，未来可能合并为统一的公司信息采集框架。

## 站点类型说明

| 类型 | 说明 | MVP 处理方式 |
|------|------|-------------|
| `static` | 静态 HTML | ✅ 支持 |
| `cms` | 动态 CMS（ASP.NET/PHP） | ✅ 支持 |
| `spa` | 前端渲染 SPA | ⚠️ 标记跳过 |
| `api` | JSON API | ⚠️ 标记跳过 |
| `blocked` | 超时/反爬/需登录 | ⚠️ 标记失败 |
| `unknown` | 未识别 | ⚠️ 尝试提取 |

## list-with-date 模式说明

### 设计原理

许多公司官网（如平安银行）的新闻列表页本身就包含完整的标题和日期信息，格式通常为：

```html
<a href="/news/detail/123">2026-08-26 平安银行发布年度报告</a>
```

本爬虫采用**结构化列表提取**策略：

1. **列表页提取**：从列表页的每个链接中尝试提取 `{url, title, published_at}`
2. **元数据传递**：将列表页提取的标题和日期传递给详情页解析器
3. **智能回退**：
   - 详情页提取成功 → 使用详情页数据
   - 详情页标题缺失或为导航文本（如「组织架构」） → 使用列表页标题
   - 详情页日期缺失 → 使用列表页日期

### 支持的日期格式

- `YYYY-MM-DD` (2026-08-26)
- `YYYY/MM/DD` (2026/08/26)
- `YYYY年M月D日` (2026年8月26日)

### 导航标题过滤

自动过滤常见的导航/静态页面标题，避免误提取：

- 组织架构、关于我们、联系方式
- 公司简介、企业文化、发展历程
- 首页、导航、菜单、网站地图
- 新闻中心、新闻列表（列表页本身）

### 分页支持

- **自动发现分页链接**：识别"下一页"、`page=N`、`index_N.html` 等模式
- **有界爬取**：通过 `--max-pages` 限制最大页数（默认 3 页）
- **去重保护**：自动跳过已访问的 URL
- **安全第一**：分页失败不影响已获取数据的处理

### 适用站点示例

- ✅ 平安银行：`2026-08-26 新闻标题` 格式
- ✅ 中兴通讯：列表页带日期的新闻条目
- ✅ 其他 CMS 站点：列表页包含摘要信息的站点

### 配置建议

```bash
# 典型 list-with-date 站点配置
python -m company_news_crawl once \
  --seed companies.json \
  --out output.jsonl \
  --max-articles 30 \
  --max-pages 3
```

## 常见问题

### Q: 为什么某些公司没有爬到文章？

A: 可能原因：
1. 站点类型为 SPA（需要浏览器）
2. 反爬机制阻断（HTTP 403/503）
3. 链接提取规则未覆盖该站点结构
4. 网络超时或连接失败

检查输出的 `errors` 和 `site_type` 字段。

### Q: 如何调整爬取速度？

A: 修改 `CRAWL_REQUEST_INTERVAL` 和 `CRAWL_TIMEOUT`。注意：
- 过快可能触发反爬
- 过慢会增加总耗时

### Q: 能否并发爬取？

A: MVP 版本为顺序执行（`max_concurrent=1`）。未来可改为 `asyncio.gather` 或 Semaphore 限流。

### Q: 如何接入 MySQL？

A: 
1. 执行 `db/schema.sql` 创建表
2. 配置环境变量 `DB_HOST`, `DB_USER` 等
3. 设置 `CRAWL_DB_ENABLED=true`
4. 实现 `db/repository.py` 中的 TODO 方法

## 下一步计划

- [ ] Playwright 集成（支持 SPA）
- [ ] 更多站点模板（ASPX、JSP 特化）
- [ ] LLM 驱动的智能链接提取
- [ ] 增量更新策略（基于 content_hash 去重）
- [ ] K8s CronJob 定时调度
- [ ] 对接 Java 任务表（统一任务队列）

## 许可证

见项目根目录 LICENSE 文件。
