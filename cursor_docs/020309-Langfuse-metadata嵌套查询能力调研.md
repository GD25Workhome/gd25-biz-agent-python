# Langfuse metadata 嵌套查询能力调研

> 调研 Langfuse DataSet Item metadata 的查询能力：UI、API、SDK 是否支持嵌套 key（如 `flow_info.flow_key`）的查询。

## 1. 结论摘要

| 能力 | 第一级 key | 嵌套 key（如 flow_info.flow_key） |
|------|------------|-----------------------------------|
| **UI 过滤** | ✅ 支持 | ❌ 不支持 |
| **API/SDK 过滤** | ✅ 支持（Traces/Observations 2025-10） | ❌ 不支持 |
| **Dataset Items** | 仅全文搜索，无结构化 metadata filter | ❌ 不支持 |
| **Full-Text Search** | 可搜索 metadata 文本内容 | 可搜索嵌套对象内的文本，但非精确 key-value 过滤 |

**核心结论**：Langfuse 官方仅支持 **metadata 第一级 key** 的精确查询，嵌套结构（如 `flow_info.flow_key`、`content_info.user_info`）无法在 UI 或 API 中直接过滤。

---

## 2. 官方文档与 Changelog 依据

### 2.1 Metadata 文档

- [Metadata - Langfuse](https://langfuse.com/docs/observability/features/metadata)
  - 说明：*"You can filter by metadata keys in the Langfuse UI and API"*
  - 未明确说明是否支持嵌套 key，实际行为为仅第一级 key

### 2.2 Traces/Observations 高级过滤（2025-10）

- [Advanced Filtering for Public Traces and Observations API](https://langfuse.com/changelog/2025-10-10-advanced-filtering-public-traces-api)
- 支持 JSON 格式 filter，示例：

```json
[
  {"type":"stringObject","column":"metadata","key":"use_case","operator":"=","value":"retrieval-augmented"}
]
```

- `key` 为 **单个 top-level metadata key**（如 `use_case`），不支持 `scope.name` 等嵌套路径

### 2.3 Dataset Items 全文搜索（2025-08）

- [Full-Text Search Across Dataset Items](https://langfuse.com/changelog/2025-08-25-full-text-search-for-dataset-items)
- 搜索范围：input、expected_output、**metadata**
- 性质：**全文搜索**（内容匹配），非按 key-value 的结构化过滤
- 可搜索 metadata 中的文本，但无法按 `flow_info.flow_key = "xxx"` 精确过滤

### 2.4 GitHub 社区讨论

- [Retrieve the trace by metadata #3276](https://github.com/orgs/langfuse/discussions/3276)：用户请求按 metadata 查询 trace，维护者表示在 roadmap
- [How to list traces with metadata filter via API or SDK #9479](https://github.com/orgs/langfuse/discussions/9479)：
  - 用户尝试过滤 `scope.name: langfuse-sdk`（嵌套 metadata）
  - 维护者 **jannikmaierhoefer** 回复：*"In this case, I would recommend filtering out the unwanted OTel traces **client-side**"*
  - 明确说明：**嵌套 metadata 过滤需在客户端自行实现**

---

## 3. 与 DataSet-metadata-schema 的对应关系

当前 schema 结构：

```json
{
  "query_message_id": "...",      // 第一级，可查询 ✅
  "query_user_id": "...",         // 第一级，可查询 ✅
  "query_flow_key": "...",        // 第一级，可查询 ✅
  "content_info": { ... },         // 嵌套，不可查询 ❌
  "flow_info": {
    "flow_key": "...",            // 嵌套，不可查询 ❌
    "flow_name": "...",           // 嵌套，不可查询 ❌
    "flow_version": "..."
  }
}
```

- `query_*` 前缀的扁平 key 是 020308 设计刻意放在根层的，目的就是**便于 Langfuse UI/API 查询**
- `flow_info.flow_key`、`flow_info.flow_name` 等嵌套字段**无法**在 UI 或 API 中直接过滤

---

## 4. 可行方案

### 4.1 方案 A：将常用查询字段提升到根层（推荐）

与 `query_flow_key` 一致，将需要查询的字段放在 metadata 根层：

```json
{
  "query_message_id": "...",
  "query_user_id": "...",
  "query_flow_key": "...",
  "query_flow_name": "...",       // 新增：从 flow_info 提升
  "query_flow_version": "...",    // 可选
  "content_info": { ... },
  "flow_info": { ... }             // 保留完整结构供展示/分析
}
```

- 优点：UI、API 均可直接按 `query_flow_name` 等过滤
- 缺点：存在一定冗余，需在写入时同步根层与 `flow_info`

### 4.2 方案 B：使用 Full-Text Search

- 在 Dataset 管理界面使用全文搜索
- 可搜索 metadata 中的文本（包括嵌套对象内的值）
- 限制：无法做 `flow_key = "xxx"` 的精确过滤，适合模糊查找

### 4.3 方案 C：API 拉取后客户端过滤

- 通过 `langfuse.api.dataset_items.list()` 拉取 items
- 在应用内按 `item.metadata.get("flow_info", {}).get("flow_key")` 等逻辑过滤
- 适用：数据量不大、需要复杂嵌套条件时

### 4.4 方案 D：向 Langfuse 提需求

- [GitHub Discussion #3276](https://github.com/orgs/langfuse/discussions/3276) 已有 metadata 过滤相关讨论
- 可补充 Dataset Items 的嵌套 metadata 过滤需求

### 4.5 方案 E：自建查询接口（直连 Postgres + JSONB）

**结论：可以支持嵌套查询。**

Langfuse 自托管时，Datasets 等事务数据存储在 **PostgreSQL** 中，metadata 通常以 **JSONB** 存储。PostgreSQL 原生支持 JSONB 的嵌套路径查询，自建查询接口完全可以实现。

#### 4.5.1 PostgreSQL JSONB 嵌套查询能力

| 能力 | 说明 | 示例 |
|------|------|------|
| `#>` / `#>>` | 路径提取 | `metadata #>> '{flow_info,flow_key}' = 'xxx'` |
| `@>` | 包含匹配 | `metadata @> '{"flow_info":{"flow_key":"xxx"}}'::jsonb` |
| `jsonb_path_query` | SQL/JSON 路径 | `jsonb_path_exists(metadata, '$.flow_info.flow_key ? (@ == "xxx")')` |
| GIN 索引 | 加速 JSONB 查询 | `CREATE INDEX ON dataset_items USING GIN (metadata jsonb_path_ops);` |

#### 4.5.2 示例 SQL

```sql
-- 按 flow_info.flow_key 精确查询
SELECT * FROM dataset_items
WHERE metadata #>> '{flow_info,flow_key}' = 'my-flow-key';

-- 按 flow_info.flow_name 模糊查询
SELECT * FROM dataset_items
WHERE metadata #>> '{flow_info,flow_name}' ILIKE '%血压%';

-- 使用 @> 包含匹配（适合多条件）
SELECT * FROM dataset_items
WHERE metadata @> '{"flow_info":{"flow_key":"my-flow","flow_name":"血压流程"}}'::jsonb;

-- 使用 jsonb_path_exists（支持更复杂条件）
SELECT * FROM dataset_items
WHERE jsonb_path_exists(metadata, '$.flow_info ? (@.flow_key == "xxx" && @.flow_name != null)');
```

#### 4.5.3 实现要点

1. **表结构**：需确认 Langfuse 实际表名与列名（如 `dataset_items`、`metadata`），可查阅 [Langfuse 源码](https://github.com/langfuse/langfuse) 或数据库 migration
2. **多租户**：Langfuse 按 project 隔离，自建接口需加上 `project_id` 等过滤
3. **部署方式**：
   - **自托管**：可直接连同一 Postgres 实例，或只读副本
   - **Langfuse Cloud**：无法直连底层数据库，此方案不适用
4. **索引**：对常用嵌套路径建表达式索引，例如：
   ```sql
   CREATE INDEX idx_metadata_flow_key
   ON dataset_items ((metadata #>> '{flow_info,flow_key}'));
   ```

#### 4.5.4 适用场景

- 自托管 Langfuse，且需要按 `flow_info.flow_key`、`content_info.user_info` 等嵌套字段查询
- 可接受在 Langfuse 之外维护一套查询 API（如 FastAPI + SQLAlchemy）
- 需要复杂组合条件（AND/OR、模糊匹配、范围查询等）

---

## 5. 参考链接

| 资源 | 链接 |
|------|------|
| Metadata 文档 | https://langfuse.com/docs/observability/features/metadata |
| Traces 高级过滤 Changelog | https://langfuse.com/changelog/2025-10-10-advanced-filtering-public-traces-api |
| Dataset Items 全文搜索 | https://langfuse.com/changelog/2025-08-25-full-text-search-for-dataset-items |
| API Reference | https://api.reference.langfuse.com |
| Trace metadata filter 讨论 | https://github.com/orgs/langfuse/discussions/9479 |
| Metadata 过滤 roadmap | https://github.com/orgs/langfuse/discussions/3276 |
| Langfuse Postgres 架构 | https://langfuse.com/self-hosting/infrastructure/postgres |
| PostgreSQL JSONB 函数与运算符 | https://www.postgresql.org/docs/current/functions-json.html |
