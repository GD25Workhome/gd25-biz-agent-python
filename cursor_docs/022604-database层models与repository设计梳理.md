# backend/infrastructure/database 层 Models 与 Repository 设计梳理

用于在设计「数据 embedding 批次」的 models 与 repository 前，统一理解当前代码的类依赖与关键字段逻辑。文档基于当前代码结构整理，便于后续 batch_job / batch_task 设计对齐现有规范。

---

## 1. 目录与职责

| 路径 | 职责 |
|------|------|
| `base.py` | SQLAlchemy `Base`、表前缀常量、`generate_ulid()` |
| `models/` | ORM 模型（表结构 + 字段），单表一文件 |
| `repository/` | 仓储：封装会话与模型，提供 CRUD 及业务查询 |
| `connection.py` / `vector_connection.py` | 数据库连接与会话管理（本文不展开） |

---

## 2. 类依赖关系

### 2.1 继承与泛型

```
Base (declarative_base)
  └── 所有 Model 类（User, DataSetsRecord, RewrittenBatchRecord, ...）

BaseRepository[ModelType]   (Generic[ModelType], model 为 Type[ModelType])
  └── 各 XxxRepository 继承并绑定具体 Model
      例：UserRepository(BaseRepository[User])
          RewrittenBatchRepository(BaseRepository[RewrittenBatchRecord])
          DataItemsRewrittenRepository(BaseRepository[DataItemsRewrittenRecord])
```

- **Model**：仅依赖 `Base` 与 `generate_ulid`（如需 ULID 主键）；不依赖其它 Model 类（外键仅声明到表名字符串）。
- **Repository**：依赖 `BaseRepository`、`AsyncSession`、以及**本表**对应 Model；若需跨表统计则再依赖其它 Model（见下）。

### 2.2 Model ↔ Repository 对应关系（核心）

| Model | Repository | 说明 |
|-------|------------|------|
| `RewrittenBatchRecord` | `RewrittenBatchRepository` | 批次表，与 DataItemsRewritten 通过 batch_code 关联 |
| `DataItemsRewrittenRecord` | `DataItemsRewrittenRepository` | 改写项表，冗余 batch_code，无批次表外键 |
| `DataSetsPathRecord` | `DataSetsPathRepository` | 路径树，无外键依赖其它 pipeline 表 |
| `DataSetsRecord` | `DataSetsRepository` | 数据集，path_id → data_sets_path.id |
| `DataSetsItemsRecord` | `DataSetsItemsRepository` | 数据项，dataset_id → data_sets.id |
| `EmbeddingRecord` | （无独立 Repository 在 __init__ 导出） | embedding 记录，source 为表名+记录 ID |
| `User` | `UserRepository` | 用户 |
| `TokenCache` / `SessionCache` | `TokenCacheRepository` / `SessionCacheRepository` | 缓存表，主键为业务 ID |
| `ImportConfigRecord` | `ImportConfigRepository` | 导入配置 |
| `KnowledgeBaseRecord` | `KnowledgeBaseRepository` | 知识库 |

### 2.3 跨 Model 的 Repository 依赖（仅读/统计）

- **RewrittenBatchRepository** 依赖 **DataItemsRewrittenRecord**：在 `get_batches_with_stats` 中按 `batch_code` 聚合统计各状态数量（init/processing/success/failed），不写 DataItemsRewritten。
- **DataItemsRewrittenRepository** 依赖 **DataSetsItemsRecord**：在 `create_init_batch` 中接收 `List[DataSetsItemsRecord]`，按条创建 DataItemsRewritten 初始记录。

其余 Repository 多为「单表 + 条件筛选」，或「树形递归」（如 DataSetsPathRepository 的 `get_tree`）。

### 2.4 表间关联（外键与逻辑关联）

- **外键（FK）**  
  - `DataSetsRecord.path_id` → `pipeline_data_sets_path.id`（ondelete=SET NULL）  
  - `DataSetsItemsRecord.dataset_id` → `pipeline_data_sets.id`（ondelete=CASCADE）  
- **无 FK、逻辑关联**  
  - `DataItemsRewrittenRecord.batch_code` 与 `RewrittenBatchRecord.batch_code` 一致，用于「批次 + 子任务」统计与查询。  
  - `DataItemsRewrittenRecord.source_dataset_id` / `source_item_id` 对应 `DataSetsRecord.id` / `DataSetsItemsRecord.id`，未建 FK。  
  - `EmbeddingRecord.source_table_name` + `source_record_id` 表示来源表与记录。

---

## 3. 关键字段逻辑（与设计规范对齐）

### 3.1 主键 id

- **类型**：`String(50)`，对应 PG `VARCHAR(50)`。  
- **生成**：`default=generate_ulid`（新建时未显式传 id 则生成 ULID）。  
- **注释**：多为 `comment="ULID"` 或 `comment="记录ID（ULID）"`。  
- **特例**：`DataSetsPathRecord.id` 可业务指定（路径拼接）；`TokenCache`/`SessionCache` 的 id 为业务键（如 token_id/session_id），长度 200。

### 3.2 时间字段

- **字段名**：`created_at` / `updated_at`（与文档中 create_time/update_time 命名不同，需在 batch 设计中二选一统一）。  
- **类型**：`DateTime(timezone=True)`（PG 建议 TIMESTAMPTZ）。  
- **创建**：`server_default=sql_func.now()`, `default=sql_func.now()`。  
- **更新**：`updated_at` 的 `onupdate=sql_func.now()`，可为 `nullable=True`。

### 3.3 表前缀

- **gd2502_**（`base.TABLE_PREFIX`）：用户、embedding、知识库、缓存等。  
- **pipeline_**（各 model 内 `PIPELINE_TABLE_PREFIX`）：data_sets_path、data_sets、data_sets_items、data_items_rewritten、rewritten_batches、import_config。

batch_job / batch_task 若归入「批次任务模块」，可沿用 pipeline_ 或单独前缀，需与 step3 设计统一。

### 3.4 状态与 JSON 字段

- **状态**：多为 `String(20)` 或 `String(100)` 存枚举值（如 init/processing/success/failed）；个别为 `SmallInteger`（如 DataSetsItemsRecord.status 1/0）。  
- **JSON**：大量使用 `JSONB`（create_params、execution_metadata、input、output、metadata_ 等）；你当前设计中的 query_params / runtime_params 若定为 JSON，与现有 JSONB 用法一致。  
- **长文本**：`Text` 用于失败原因、堆栈、embedding_str 等。

### 3.5 批次 + 子任务模式（可复用到 batch_job / batch_task）

- **批次表**（如 RewrittenBatchRecord）：id、batch_code（唯一）、total_count、create_params（JSON）、status、created_at、updated_at。无「子任务表」外键。  
- **子任务表**（如 DataItemsRewrittenRecord）：id、batch_code（冗余）、status、execution_metadata（JSON）、来源字段（source_dataset_id、source_item_id）等。通过 **batch_code** 与批次表关联；Repository 层按 batch_code 做统计或批量查询。  
- **统计方式**：RewrittenBatchRepository 在 `get_batches_with_stats` 中按 `DataItemsRewrittenRecord.batch_code` 聚合 count 与各 status 的 sum，再与批次记录组合返回。

---

## 4. Repository 核心方法模式

### 4.1 BaseRepository 提供

- `get_by_id(id: str) -> Optional[ModelType]`  
- `get_all(limit, offset) -> List[ModelType]`  
- `create(**kwargs) -> ModelType`  
- `update(id: str, **kwargs) -> Optional[ModelType]`（仅更新非 None 的 kwargs）  
- `delete(id: str) -> bool`  

所有子类通过 `super().__init__(session, SomeRecord)` 绑定 Model，并可直接使用以上方法。

### 4.2 子类扩展典型方法

- **按业务键查询**：如 `get_by_batch_code`、`get_by_user_name`、`get_by_source_ids`。  
- **分页列表 + total**：`get_list_with_total` / `get_list_with_total_optional_dataset`，条件拼接 + `func.count()` + `limit/offset`。  
- **业务写操作**：如 `create_init_batch`（批量创建子任务）、`update_status`、`update_status_to_processing_if_init`。  
- **跨表只读**：如 `get_batches_with_stats`（批次 + 子任务状态聚合），返回 dataclass 或 tuple 列表。  
- **树/递归**：如 DataSetsPathRepository 的 `get_children_by_path`、`get_tree`。

### 4.3 状态常量

- 子任务状态集中在 Repository 或共享常量（如 DataItemsRewrittenRepository 的 STATUS_INIT / STATUS_PROCESSING / STATUS_SUCCESS / STATUS_FAILED），与 Model 的 status 字段取值一致，便于条件与统计复用。

---

## 5. 与 batch_job / batch_task 设计的对照建议

- **主键**：id 使用 `VARCHAR(50)` + ULID，与现有 Model 一致。  
- **时间**：若与现有表统一用 `created_at`/`updated_at` + `DateTime(timezone=True)`；若沿用 022603 文档则用 create_time/update_time，需在实现时与项目约定统一。  
- **批次表**：类似 RewrittenBatchRecord，提供 code、total_count、query_params（JSON）；可增加 version、is_deleted 等基础字段（当前 rewritten 表未用 is_deleted，可按需引入）。  
- **子任务表**：类似 DataItemsRewrittenRecord，通过 **job_id** 关联 batch_job（建议 FK 到 batch_job.id），同时保留 source_table_id、source_table_name、status、runtime_params、execution_result、execution_error_message、execution_return_key 等；冗余 key 用于去重/幂等。  
- **Repository**：BatchJobRepository 继承 BaseRepository，提供 get_by_code、get_list、create 等；BatchTaskRepository 继承 BaseRepository，提供按 job_id 查询、按状态更新、批量创建等；若需「批次+子任务统计」，可仿 RewrittenBatchRepository.get_batches_with_stats 跨表聚合。  
- **跨表统计**：若 batch_task 与 batch_job 为 FK 关联，统计可直接按 job_id 分组；若沿用「冗余 code」模式，也可按 code 聚合，与现有 rewritten 模式一致。

以上为当前 database 层 models 与 repository 的设计梳理，便于在后续文档中写出 batch_job / batch_task 的 models 与 repository 核心逻辑设计。
