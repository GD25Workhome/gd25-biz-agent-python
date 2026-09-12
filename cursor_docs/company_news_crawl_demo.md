# company_news_crawl MVP 演示文档

## 快速开始示例

### 1. 安装依赖

```bash
# 进入项目根目录
cd /workspace

# 安装爬虫依赖
pip install -r company_news_crawl/requirements.txt
```

### 2. 查看帮助

```bash
python3 -m company_news_crawl --help
```

输出：
```
usage: __main__.py [-h] {once} ...

A股上市公司官网新闻爬虫 MVP

positional arguments:
  {once}      子命令
    once      执行一次爬取

options:
  -h, --help  show this help message and exit
```

### 3. 运行示例爬取

```bash
python3 -m company_news_crawl once \
  --seed company_news_crawl/examples/seed_sample.json \
  --out /tmp/company_news_output.jsonl \
  --max-articles 5
```

### 4. 查看结果

#### 汇总统计

```bash
cat /tmp/company_news_output_summary.json
```

示例输出：
```json
{
  "total_companies": 7,
  "successful_companies": 5,
  "total_articles": 22,
  "total_errors": 5,
  "companies": [
    {
      "stock_code": "000001",
      "company_name": "平安银行",
      "article_count": 5,
      "error_count": 0,
      "site_type": "static",
      "list_url": "http://bank.pingan.com/bankPingAnCom/about/news"
    },
    ...
  ]
}
```

#### 详细数据

```bash
# 查看前 10 行
head -10 /tmp/company_news_output.jsonl

# 统计各类型记录数量
echo "Profile 记录数: $(grep '"type": "profile"' /tmp/company_news_output.jsonl | wc -l)"
echo "Article 记录数: $(grep '"type": "article"' /tmp/company_news_output.jsonl | wc -l)"
echo "Error 记录数: $(grep '"type": "errors"' /tmp/company_news_output.jsonl | wc -l)"

# 查看某篇文章详情（格式化输出）
grep '"type": "article"' /tmp/company_news_output.jsonl | head -1 | python3 -m json.tool
```

## 真实运行结果展示

### 测试环境

- Python: 3.12.3
- 依赖: httpx 0.27+, selectolax 0.3+, trafilatura 1.10+
- 测试时间: 2026-09-12
- 测试样本: 7 家 A 股上市公司

### 运行统计

```
=== 统计 ===
公司总数: 7
成功公司: 5
文章总数: 22
```

### 成功案例

| 股票代码 | 公司名称 | 文章数 | 站点类型 | 备注 |
|---------|---------|--------|---------|------|
| 000001 | 平安银行 | 5 | static | ✅ 完全成功 |
| 000031 | 大悦城 | 2 | static | ⚠️ 部分页面提取失败 |
| 000055 | 方大集团 | 5 | static | ✅ 完全成功 |
| 000333 | 美的集团 | 5 | static | ✅ 完全成功 |
| 000411 | 英特集团 | 5 | cms | ✅ 完全成功（ASPX 站点） |

### 预期失败案例

| 股票代码 | 公司名称 | 失败原因 | 站点类型 |
|---------|---------|---------|---------|
| 000034 | 神州数码 | HTTP 521（可能需要特定 Cookie） | unknown |
| 000063 | 中兴通讯 | 站点结构未识别 | unknown |

## 输出格式详解

### 1. Profile 记录（站点档案）

```json
{
  "type": "profile",
  "data": {
    "stock_code": "000001",
    "company_name": "平安银行",
    "list_url": "http://bank.pingan.com/bankPingAnCom/about/news",
    "site_type": "static",
    "last_http_status": 200,
    "last_article_link_count": 103,
    "last_success_at": "2026-09-12T04:39:34.760193",
    "fail_streak": 0,
    "notes": ""
  }
}
```

**字段说明**：
- `site_type`: 站点类型识别结果（static/cms/spa/api/blocked/unknown）
- `last_article_link_count`: 列表页提取到的候选链接数
- `last_success_at`: 最后成功爬取时间
- `fail_streak`: 连续失败次数

### 2. Article 记录（文章内容）

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
    "fetched_at": "2026-09-12T04:40:10.123456",
    "content_text": "正文内容（完整文本）...",
    "content_hash": "a1b2c3d4e5f6...",
    "summary": "前200字摘要...",
    "http_status": 200,
    "fetch_method": "http",
    "template_id": "generic",
    "site_type": "static",
    "parse_version": "company_news_mvp_v1"
  }
}
```

**关键字段**：
- `source_level`: 固定为 `P0_official_site`（官网一级来源）
- `content_hash`: SHA256 哈希，用于去重
- `summary`: 自动生成的前 200 字摘要
- `published_at`: 从页面提取的发布日期（可能为 null）
- `parse_version`: 解析版本标识，便于后续升级迭代

### 3. Errors 记录（错误日志）

```json
{
  "type": "errors",
  "stock_code": "000031",
  "errors": [
    "Failed to extract content from http://www.grandjoy.com/detail/308.html",
    "Failed to extract content from http://www.grandjoy.com/detail/309.html"
  ]
}
```

## 高级用法

### 自定义爬取参数

```bash
# 每家公司最多爬 10 篇，超时 15 秒
python3 -m company_news_crawl once \
  --seed my_companies.json \
  --out result.jsonl \
  --max-articles 10 \
  --timeout 15
```

### 使用环境变量配置

创建 `.env` 文件：

```bash
CRAWL_MAX_ARTICLES=30
CRAWL_TIMEOUT=20
CRAWL_REQUEST_INTERVAL=2.0
CRAWL_OUTPUT_DIR=/data/crawl
```

运行：

```bash
python3 -m company_news_crawl once --seed seed.json --out out.jsonl
```

### 准备自己的种子文件

#### JSON 格式

```json
[
  {
    "stock_code": "000001",
    "company_name": "平安银行",
    "news_list_url": "http://bank.pingan.com/bankPingAnCom/about/news"
  },
  {
    "stock_code": "600000",
    "company_name": "浦发银行",
    "news_list_url": "https://www.spdb.com.cn/about/news/"
  }
]
```

#### JSONL 格式

```jsonl
{"stock_code": "000001", "company_name": "平安银行", "news_list_url": "http://..."}
{"stock_code": "600000", "company_name": "浦发银行", "news_list_url": "https://..."}
```

## 数据后续处理示例

### Python 读取结果

```python
import json

# 读取文章
articles = []
with open('/tmp/company_news_output.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        record = json.loads(line)
        if record['type'] == 'article':
            articles.append(record['data'])

print(f"共读取 {len(articles)} 篇文章")

# 按公司分组
from collections import defaultdict
by_company = defaultdict(list)
for article in articles:
    by_company[article['company_name']].append(article)

for company, arts in by_company.items():
    print(f"{company}: {len(arts)} 篇")
```

### 导入 MySQL（未来）

```bash
# 1. 创建表结构
mysql -u root -p company_news < company_news_crawl/db/schema.sql

# 2. 编写导入脚本或实现 repository.py 中的方法
# 3. 基于 content_hash 去重插入
```

### 对接知识库

```python
# 示例：转换为 RAG 系统所需格式
for article in articles:
    document = {
        "doc_id": article['content_hash'],
        "title": article['title'],
        "content": article['content_text'],
        "metadata": {
            "source": "official_site",
            "company": article['company_name'],
            "stock_code": article['stock_code'],
            "published_at": article['published_at'],
            "url": article['article_url'],
        }
    }
    # 插入向量数据库...
```

## 测试说明

### 运行单元测试

```bash
cd /workspace
python3 -m pytest company_news_crawl/tests/ -v
```

预期输出：
```
============================= test session starts ==============================
collected 7 items

company_news_crawl/tests/test_content_extractor.py::test_extract_title_from_fixture PASSED
company_news_crawl/tests/test_content_extractor.py::test_extract_content_from_fixture PASSED
company_news_crawl/tests/test_content_extractor.py::test_generate_summary PASSED
company_news_crawl/tests/test_list_extractor.py::test_extract_links_basic PASSED
company_news_crawl/tests/test_list_extractor.py::test_normalize_url PASSED
company_news_crawl/tests/test_list_extractor.py::test_extract_links_same_domain_filter PASSED
company_news_crawl/tests/test_list_extractor.py::test_extract_links_keywords_priority PASSED

============================== 7 passed in 0.48s
```

### 测试覆盖说明

- ✅ URL 规范化（去 fragment、统一大小写）
- ✅ 同域名过滤
- ✅ 新闻关键词优先级排序
- ✅ 标题提取（多种 fallback）
- ✅ 正文提取（trafilatura + 回退逻辑）
- ✅ 摘要生成（截断 + 省略号）

## 常见问题

### Q: 为什么某些公司没有爬到文章？

**A**: 可能原因及排查步骤：

1. 检查输出中的 `site_type`：
   - `spa`: 需要浏览器渲染（MVP 不支持）
   - `blocked`: HTTP 错误或反爬
   - `unknown`: 站点结构未识别

2. 查看 errors 记录：
   ```bash
   grep '"type": "errors"' output.jsonl
   ```

3. 手动访问 `list_url` 确认是否需要登录/Cookie

### Q: 如何提高爬取成功率？

**A**: 当前 MVP 建议：

1. 调整超时时间：`--timeout 30`
2. 增加请求间隔（环境变量）：`CRAWL_REQUEST_INTERVAL=3.0`
3. 检查网络连通性
4. 对于 SPA 站点，等待后续 Playwright 集成

### Q: 可以并发爬取吗？

**A**: MVP 版本为顺序执行（`max_concurrent=1`），避免以下问题：
- 触发网站反爬
- 并发控制复杂度

未来可改为 `asyncio.gather` + `Semaphore` 限流。

### Q: 与 radar_crawl 有什么区别？

**A**: 

| 维度 | radar_crawl | company_news_crawl |
|------|------------|-------------------|
| 数据源 | 巨潮资讯网（公告） | 公司官网（新闻） |
| 来源级别 | P1/P2 | P0 |
| 数据格式 | PDF + 结构化 | HTML 转文本 |
| 任务调度 | MySQL 队列 | 单次运行 |

两者互补，未来可能合并为统一框架。

## 下一步改进方向

1. **Playwright 集成** - 支持 SPA 站点
2. **更多模板** - 针对 ASPX/JSP 等特定 CMS 的优化规则
3. **智能提取** - LLM 辅助链接识别和内容提取
4. **增量更新** - 基于 content_hash 避免重复爬取
5. **调度集成** - K8s CronJob 或统一任务队列
6. **监控告警** - 失败率监控、异常站点告警

## 参考资源

- 包文档: `company_news_crawl/README.md`
- 数据库 schema: `company_news_crawl/db/schema.sql`
- 测试用例: `company_news_crawl/tests/`
- PR: https://github.com/GD25Workhome/gd25-biz-agent-python/pull/51
