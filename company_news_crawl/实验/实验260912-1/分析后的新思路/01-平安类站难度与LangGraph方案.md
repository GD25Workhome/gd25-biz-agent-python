# 平安类站：难度与 LangGraph 方案

## 难度判定

相对大悦城（门户聚合）、神州数码（卡片+产品污染）：

- **列表页**：标准新闻归档；每条「日期 + 标题链接」；分页（首页/上一页/页码/下一页/尾页）清晰 → **普通偏易**  
- **详情页**：存在小坑（标题常在 h3、日期为裸 h5、同页噪声模块）→ 仍属普通，用列表字段兜底 + 轻模板即可  
- **总评**：规则友好型样板站；反爬/SPA 不是主矛盾。主问题是 **翻页跑全 + 字段抽干净**。

## 设计原则

- 列表页把 **标题、日期、URL 一次采齐**（详情抽挂了也有结果）  
- LangGraph 负责分页循环、质检分支、可观测；**80%～90% 节点确定性**  
- LLM 只处理质量门失败样本，不负责日常探索整站  

## 推荐图（节点）

```
START
  → resolve_site_profile       # 标记 family=list_with_date / template
  → fetch_list_page            # GET 当前列表 URL
  → parse_list_items           # 规则抽出 {url, title, date}
  → enqueue_pagination         # index_N / 下一页入队（max_pages）
  → 还有列表页？ → fetch_list_page
  → fetch_article              # GET 详情
  → extract_article_fields     # 正文为主；标题/日期优先用列表字段
  → quality_gate
       ├─ pass → write_sink
       └─ fail → llm_repair → write_sink
  → END
```

### 节点要点

| 节点 | 作用 |
|------|------|
| parse_list_items | 不要只捞 href；从列表项解析 url + 去日期后的 title + YYYY-MM-DD |
| enqueue_pagination | 静态分页硬顶（页数或近 N 个月） |
| extract_article_fields | 列表字段兜底；详情轻选择器补正文/校正 |
| quality_gate | 日期空、标题像导航词、正文过短/像许可证公示 → 失败 |
| llm_repair | 输入 HTML 片段+列表锚文本；强制 JSON；日期须能指回原文 |

## 相对当前 MVP 的收益

| 能力 | 现 MVP | 本方案 |
|------|--------|--------|
| 第一页新闻链 | 能抓到 | 同样能，并带列表日期/标题 |
| 翻页 | 无 | 规则翻页 |
| 详情日期/标题 | 常空/常错 | 列表兜底 + 轻模板 + 失败 LLM |
| 成本 | 低 | 仍低 |

## 适用边界

适用于「列表即档案、日期标题可见、分页可枚举」的站。  
门户入口、强 JS 分页、卡片混产品区 → 不按本图硬套，见后续难站旁路。
