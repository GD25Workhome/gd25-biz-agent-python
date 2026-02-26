# gd2502_embedding_records 表数据存储代码流程总结

## 1. 表与模型

- **物理表名**：`gd2502_embedding_records`（前缀来自 `TABLE_PREFIX`）
- **ORM 模型**：`backend/infrastructure/database/models/embedding_record.py` 中的 `EmbeddingRecord`
- **用途**：存储“词干提取后的结构化数据”及对应 2048 维 embedding 向量，供 RAG 案例检索使用。

### 1.1 主要字段（概要）

| 字段 | 说明 |
|------|------|
| id | 记录 ID（ULID），主键 |
| scene_summary | 场景摘要 |
| optimization_question | 优化后的问题 |
| input_tags / response_tags | 标签（JSON 数组字符串） |
| ai_response | AI 回复内容 |
| embedding_str | 用于生成 embedding 的拼接文本 |
| embedding_value | 2048 维向量（pgvector） |
| message_id / trace_id | 消息 ID、Trace ID（可观测） |
| version | 版本号（按 source 递增） |
| source_table_name / source_record_id | 数据来源表与记录 ID |
| generation_status | 0=进行中，1=成功，-1=失败 |
| failure_reason | 失败原因/堆栈 |
| is_published / created_at / updated_at | 发布标记与时间 |

---

## 2. 写入流程（Pipeline）

写入由 **embedding 流程** 完成，涉及两个节点：先插入“进行中”记录，再更新向量与状态。

### 2.1 流程配置

- 主流程：`config/flows/embedding_knowledge_agent/flow.yaml`
- 节点顺序：`before_embedding_func` → embedding 节点 → `insert_data_to_vector_db`

### 2.2 节点一：before_embedding_func（插入记录）

**文件**：`backend/domain/flows/implementations/before_embedding_func.py`

**职责**：只做“插入一条 embedding 记录 + 生成 embedding_str”，不查业务表，数据全部来自 state。

**流程概要**：

1. **读 state**
   - `edges_var`：`scene_summary`、`optimization_question`、`input_tags`、`response_tags`、`ai_response`
   - `prompt_vars`：`source_id`、`source_table_name`（数据来源）
   - 可选：`trace_id`

2. **校验**：`source_id`、`source_table_name` 必填。

3. **版本号**：按 `(source_record_id, source_table_name)` 在 **本表** 查 `max(version)`，新记录为 `max+1`（从 0 起）。

4. **生成 embedding_str**：  
   `scene_summary` + `"问题：" + optimization_question` + `"回复：" + ai_response`，用换行拼接。

5. **插入**：  
   构造 `EmbeddingRecord`（含上述字段 + `embedding_str`，`embedding_value` 为空，`generation_status=0` 进行中），`session.add` → `flush` → `refresh`。

6. **写回 state**
   - `edges_var["embedding_str"]` = 上面生成的字符串
   - `prompt_vars["embedding_records_id"]` = 新记录的 `id`

7. **提交**：`session.commit()`。

**结果**：表中多一条“进行中”记录，流程把 `embedding_records_id` 带给下游节点。

### 2.3 节点二：insert_data_to_vector_db（更新向量与状态）

**文件**：`backend/domain/flows/implementations/insert_data_to_vector_db_func.py`

**职责**：根据 `embedding_records_id` 找到该条记录，写入 `embedding_value` 并把 `generation_status` 置为成功（或失败时置为失败并写 `failure_reason`）。

**流程概要**：

1. **读 state**
   - `edges_var["embedding_value"]`：上游 embedding 节点产出的向量（list/tuple）
   - `prompt_vars["embedding_records_id"]`：本表记录 ID

2. **校验**：  
   `embedding_value` 非空、`embedding_records_id` 非空，且 `embedding_value` 为 list 或 tuple。

3. **查库**：  
   `select(EmbeddingRecord).where(EmbeddingRecord.id == embedding_records_id)`，拿不到则报错。

4. **更新**
   - `embedding_record.embedding_value = list(embedding_value)`
   - `embedding_record.generation_status = 1`
   - `embedding_record.failure_reason = None`

5. **提交**：`session.commit()`。

6. **异常时**：  
   若本节点执行失败，在 catch 里再开 session，用同一 `embedding_records_id` 把该记录的 `generation_status = -1`、`failure_reason = 堆栈` 并 commit。

**结果**：同一条记录从“进行中”变为“成功”（或“失败”），并持久化向量。

---

## 3. 读取 / 使用流程

### 3.1 RAG 案例检索（向量相似度）

**文件**：`backend/domain/flows/nodes/rag_agent_creator.py` 中的 `_search_similar_cases`

**行为**：

- 使用表名 `TABLE_PREFIX + "embedding_records"`（即 `gd2502_embedding_records`）。
- 用 **psycopg + pgvector** 直连数据库，执行 SQL：
  - 条件：`embedding_value IS NOT NULL`，且 `1 - (embedding_value <=> $query_vector) >= threshold`
  - 排序：`embedding_value <=> $query_vector`（按距离）
  - 取 top_k。
- 降级策略：若结果不足，依次降低相似度阈值（如 -0.1、-0.2），最低 0.3。
- 返回字段：`id`、`scene_summary`、`optimization_question`、`ai_response`、相似度分数。

即：**读** 只依赖本表中已写入的 `embedding_value` 和业务字段，用于 RAG 检索相似案例。

### 3.2 知识库导入脚本（排除已处理）

**文件**：`scripts/embedding_import_qa/core/repository.py`

**函数**：`fetch_records_excluding_processed(limit, offset)`

**行为**：

- 查的是 **知识库表**（如 `KnowledgeBaseRecord`），不是直接查 `embedding_records`。
- 通过 **LEFT JOIN embedding_records**：  
  `EmbeddingRecord.source_table_name == 知识库表名` 且 `EmbeddingRecord.source_record_id == KnowledgeBaseRecord.id`，再 `WHERE EmbeddingRecord.id IS NULL`。
- 得到“尚未在 embedding_records 中有对应记录”的知识库行，避免重复跑 embedding 流程。

即：**读** embedding_records 的 `source_table_name`、`source_record_id`，用于判断某条知识库记录是否已经做过 embedding 并写入本表。

---

## 4. 数据流总览

```
[知识库/业务表]
       │
       ▼
fetch_records_excluding_processed  (LEFT JOIN embedding_records 排除已处理)
       │
       ▼
embedding 流程 state 初始化 (edges_var, prompt_vars)
       │
       ▼
before_embedding_func  ──►  INSERT 一条记录 (status=0)，写入 embedding_str
       │                      state.prompt_vars["embedding_records_id"] = id
       ▼
embedding 节点  ──►  根据 embedding_str 生成向量，写入 edges_var["embedding_value"]
       │
       ▼
insert_data_to_vector_db  ──►  按 embedding_records_id 更新该条记录
                                 (embedding_value, generation_status=1 或 -1)
       │
       ▼
gd2502_embedding_records 中一条完整记录（含向量）
       │
       ▼
RAG 检索 (_search_similar_cases) 使用 embedding_value 做相似度检索
```

---

## 5. 涉及文件一览

| 类型 | 文件路径 |
|------|----------|
| 模型定义 | `backend/infrastructure/database/models/embedding_record.py` |
| 表创建/迁移 | `alembic/versions/9a6d8edb7942_add_embedding_records_table.py` 及后续若干迁移（如 embedding_str、embedding_value、ai_response、trace_id） |
| 写入-插入 | `backend/domain/flows/implementations/before_embedding_func.py` |
| 写入-更新 | `backend/domain/flows/implementations/insert_data_to_vector_db_func.py` |
| 流程配置 | `config/flows/embedding_knowledge_agent/flow.yaml` |
| 读取-检索 | `backend/domain/flows/nodes/rag_agent_creator.py`（`_search_similar_cases`） |
| 读取-排除已处理 | `scripts/embedding_import_qa/core/repository.py`（`fetch_records_excluding_processed`） |

---

## 6. 小结

- **gd2502_embedding_records** 的 **写** 由 embedding 流程的两步完成：  
  **before_embedding_func** 插入一条进行中记录并生成 `embedding_str`，**insert_data_to_vector_db** 根据 `embedding_records_id` 回写向量与成功/失败状态。
- **读** 有两类：  
  1）RAG 按 `embedding_value` 做向量相似度检索；  
  2）知识库导入脚本通过 `source_table_name` + `source_record_id` 判断哪些知识库记录尚未在本表落库，从而避免重复处理。
