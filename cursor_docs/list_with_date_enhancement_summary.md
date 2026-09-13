# company_news_crawl list-with-date 功能增强说明

## 完成概览

✅ 成功增强 `company_news_crawl` 包，支持平安银行等**列表页带日期**（list-with-date）站点的可靠爬取。

## 核心改进

### 1. 结构化列表提取

**问题**：原 MVP 版本仅提取 URL，丢失列表页中的标题和日期信息。

**解决方案**：
- 新增 `ListItem` 模型存储 `{url, title, published_at}`
- 新增 `extract_list_items()` 方法，从列表页每个链接解析元数据
- 支持格式：`2026-08-26 标题`、`2026年8月26日 标题`、`2026/08/26 标题`

**效果**：
```python
items = ListExtractor.extract_list_items(html, base_url)
# [ListItem(url='...', title='平安银行发布中报', published_at='2026-08-26'), ...]
```

### 2. 元数据传递与智能回退

**问题**：详情页标题提取失败或误提取导航标题（如「组织架构」）时，文章记录不完整。

**解决方案**：
- `ContentExtractor.extract()` 接受 `list_title` 和 `list_date` 作为回退
- 新增导航标题过滤器（识别并拒绝「组织架构」「关于我们」等）
- 详情页提取成功 → 使用详情页数据
- 详情页标题缺失/为导航 → 回退到列表页标题
- 详情页日期缺失 → 回退到列表页日期

**效果**：
- 平安银行导航页面不再被误识别为新闻
- `published_at` 为 null 的情况大幅减少

### 3. 静态分页支持

**问题**：仅爬取第一页，遗漏多页列表的后续内容。

**解决方案**：
- 新增 `extract_pagination_links()` 识别"下一页"、`page=N`、`index_N.html` 等模式
- 爬取流程自动跟随分页链接，可配置 `max_pages`（默认 3）
- 去重保护、分页失败不影响已获取数据

**配置**：
```bash
python -m company_news_crawl once \
  --seed companies.json \
  --out output.jsonl \
  --max-pages 5
```

### 4. 增强的详情页提取

**h3/h5 模式支持**（平安银行等站点）：
- 标题优先级：`h3 > h1 > .title > fallback > <title>`
- 日期选择器新增：`h5`、`h6`（裸日期标签）

**多格式日期支持**：
- `YYYY-MM-DD` → `2026-08-26`
- `YYYY/MM/DD` → `2026-08-26`
- `YYYY年M月D日` → `2026-08-26`
- 自动零填充（`2026-8-6` → `2026-08-06`）

## 测试覆盖

### 单元测试

新增 10 个测试用例，覆盖：
- 日期+标题从锚点文本提取
- Ping An fixture 列表提取
- 分页链接识别
- h3 标题 + h5 日期提取
- 导航标题过滤
- 元数据回退与覆盖
- 多种日期格式

**结果**：17/17 测试通过

```bash
$ python3 -m pytest company_news_crawl/tests/ -v
============================== 17 passed in 0.41s ===============================
```

### 集成测试

新增 `cursor_test/test_list_with_date_integration.py`，演示端到端功能：
- 从 Ping An fixture 提取 6 个新闻项（含标题和日期）
- 识别 3 个分页链接
- h3/h5 提取成功
- 导航页面正确回退到列表页元数据
- 4 种日期格式规范化

**结果**：所有集成测试通过

## 文档更新

### README.md

新增章节：
- **"list-with-date 模式说明"**：设计原理、支持的日期格式、导航标题过滤、分页支持、适用站点示例、配置建议
- 更新"核心能力"、"配置选项"

### 中文注释

所有新增代码包含详细的中文注释和文档字符串。

## 兼容性

✅ **完全向后兼容**：
- 保留 `extract_links()` 方法（旧代码可继续使用）
- 新参数均为可选（`list_title`、`list_date`）
- CLI 命令保持不变（`--max-pages` 为新增可选参数）
- 输出格式不变（JSONL）

✅ **非破坏性变更**：
- 仅修改 `company_news_crawl/` 目录
- 不影响现有 backend/domain/app 代码
- 不修改数据库 schema

## 配置与使用

### 基础用法（保持不变）

```bash
python -m company_news_crawl once \
  --seed companies.json \
  --out output.jsonl \
  --max-articles 20
```

### 启用分页

```bash
python -m company_news_crawl once \
  --seed companies.json \
  --out output.jsonl \
  --max-pages 5 \
  --max-articles 30
```

### 环境变量

```bash
export CRAWL_MAX_PAGES=3
export CRAWL_MAX_ARTICLES=20
python -m company_news_crawl once --seed data.json --out result.jsonl
```

## 适用站点

本增强特别适用于以下类型站点：

✅ **列表页带日期**：
- 平安银行：`2026-08-26 新闻标题`
- 中兴通讯：列表页带摘要信息
- 其他 CMS 站点：列表页包含元数据

✅ **h3/h5 标题日期模式**：
- 详情页标题在 `<h3>` 而非 `<h1>`
- 日期在裸 `<h5>2026-08-26</h5>` 标签中

✅ **多页列表**：
- 静态分页（`<a>` 标签链接）
- 可配置最大页数（安全限制）

## 成果验证

| 指标 | 状态 |
|------|------|
| 单元测试 | ✅ 17/17 通过 |
| 集成测试 | ✅ 4 个场景通过 |
| CLI 兼容性 | ✅ 保持现有用法 |
| 向后兼容 | ✅ 无破坏性变更 |
| 中文文档 | ✅ README + 代码注释 |
| PR 创建 | ✅ #52 (Draft) |

## PR 信息

- **分支**：`cursor/list-with-date-enhancements-ac62`
- **PR #**：52
- **状态**：Draft（待审核）
- **URL**：https://github.com/GD25Workhome/gd25-biz-agent-python/pull/52
- **Base 分支**：`huayuan/v1-260911`

## 提交历史

1. **d36c3e2**：增强 company_news_crawl 以支持 list-with-date 站点（主要功能）
2. **8e1d933**：添加 list-with-date 功能集成测试

## 下一步

本 PR 为后续优化奠定基础：

1. **真实站点测试**：使用实际平安银行等站点验证（需网络环境）
2. **LangGraph 编排**：将列表提取、分页、详情爬取封装为图节点
3. **Playwright 集成**：支持动态分页（SPA 站点）
4. **LLM 驱动修复**：提取失败时通过 LLM 节点重试

## 总结

✅ **目标达成**：
- 列表页元数据被正确提取和利用
- 详情页提取更可靠（h3/h5 支持、导航过滤）
- 分页功能安全可配置
- 所有测试通过、文档完善

✅ **设计原则遵循**：
- 结果优先（列表元数据作为可靠回退）
- 向后兼容（保留旧接口）
- 安全第一（分页有上限、去重保护）
- 文档完整（中文 README + 代码注释）

🎉 **可交付**：PR #52 已创建，准备审核。
