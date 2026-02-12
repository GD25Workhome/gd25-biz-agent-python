# Rewritten 批次表与创建流程设计

## 1. 概述

### 1.1 背景

当前 `rewritten_service.py` 中，每次调用 `create_rewritten_batch` 时会生成一个 `batch_code`（格式：`YYYYMMDDHHmmss`），同一轮创建的数据项共用该 code。但该 code 仅存在于 `pipeline_data_items_rewritten` 表中，缺乏 centralized 管理，无法记录批次级别的元数据（如数据总量、创建参数等），也不便于后续界面做更多交互。

### 1.2 目标

1. **新建批次表**：集中管理 batch_code，记录数据总量及创建参数。
2. **参数 JSON 存储**：考虑到创建参数的灵活性和未来扩展，采用 JSONB 格式存储。
3. **改造创建流程**：在 `create_rewritten_batch` 中，生成 batch_code 时同时写入批次表。
4. **为后续 UI 预留**：批次表数据可供前端做批次列表、进度统计、参数回放等交互。

### 1.3 参考文档

- `cursor_docs/021001-Rewritten流程批量异步执行技术设计.md`：现有批量创建与 Worker 流程设计。

---

## 2. 批次表设计

### 2.1 表名与命名

| 项目 | 取值 |
|------|------|
| 表名 | `pipeline_rewritten_batches` |
| 模型类 | `RewrittenBatchRecord` |
| 仓储类 | `RewrittenBatchRepository` |

遵循现有 `pipeline_` 前缀约定（与 `pipeline_data_items_rewritten` 一致）。

### 2.2 字段设计

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `id` | String(50) | 否 | 主键，ULID |
| `batch_code` | String(100) | 否 | 批次编码，唯一，索引；格式 `YYYYMMDDHHmmss` |
| `total_count` | Integer | 否 | 本批次数据项总量 |
| `create_params` | JSONB | 是 | 创建参数，JSON 格式；见 2.3（含 dataset_id/dataset_ids 等） |
| `status` | String(20) | 是 | 可选，批次级状态；默认可留空，后续扩展 |
| `created_at` | DateTime(tz) | 否 | 创建时间 |
| `updated_at` | DateTime(tz) | 是 | 更新时间 |

**说明**：`dataset_id` 不作为独立字段。未来批次可能包含多数据集，或与数据集无强绑定，故将 `dataset_id` / `dataset_ids` 等放入 `create_params` 中，保持表结构灵活。

### 2.3 create_params 结构（JSON）

创建参数具有自由性，采用 JSON 存储。建议约定结构如下，后续可扩展：

```json
{
  "dataset_id": "xxx",
  "mode": "item_ids | query_params",
  "item_ids": ["id1", "id2"],
  "query_params": {
    "status": 1,
    "unique_key": "xxx",
    "source": "xxx",
    "keyword": "xxx"
  }
}
```

- **dataset_id**：可选，单数据集时填写。未来若支持多数据集，可扩展为 `dataset_ids` 数组。
- **mode**：创建模式。`item_ids` 表示按 ID 列表；`query_params` 表示按条件筛选。
- **item_ids**：`mode=item_ids` 时填写，字符串数组。
- **query_params**：`mode=query_params` 时填写，对象，对应 `RewrittenExecuteQueryParams` 的 `model_dump(exclude_unset=True)` 结果。

若后续新增参数（如分页、自定义筛选、多数据集），只需在 JSON 中增加字段即可，无需改表结构。

---

## 3. rewritten_service 创建流程改造

### 3.1 当前流程（简要）

```
create_rewritten_batch(dataset_id, session, item_ids?, query_params?)
  → 查询 data_sets_items 得到 records
  → batch_code = datetime.now().strftime("%Y%m%d%H%M%S")
  → rewritten_repo.create_init_batch(records, batch_code, dataset_id)
  → 返回 RewrittenBatchCreateResult(batch_code, total)
```

### 3.2 改造后流程

```
create_rewritten_batch(dataset_id, session, item_ids?, query_params?)
  → 查询 data_sets_items 得到 records
  → batch_code = datetime.now().strftime("%Y%m%d%H%M%S")
  → create_params = _build_create_params(dataset_id, item_ids, query_params)
  → 1. batch_repo.create(batch_code, total_count, create_params)  [新增]
  → 2. rewritten_repo.create_init_batch(records, batch_code, dataset_id)
  → 返回 RewrittenBatchCreateResult(batch_code, total)
```

要点：

- 先创建批次表记录，再创建 rewritten 记录，保证 batch_code 与批次元数据一一对应。
- `dataset_id` 纳入 `create_params`，不单独存表。
- 若 `create_init_batch` 实际创建数为 0（因去重跳过），`total_count` 仍以 records 数量为准，或根据需要改为实际 created 数，需与业务约定一致。

### 3.3 create_params 构建逻辑

```python
def _build_create_params(
    dataset_id: Optional[str] = None,
    item_ids: Optional[List[str]] = None,
    query_params: Optional[Dict[str, Any]] = None,
) -> dict:
    """构建 create_params JSON。"""
    base: Dict[str, Any] = {}
    if dataset_id:
        base["dataset_id"] = dataset_id
    if item_ids is not None:
        base["mode"] = "item_ids"
        base["item_ids"] = item_ids
        return base
    if query_params is not None:
        base["mode"] = "query_params"
        base["query_params"] = query_params
        return base
    return base
```

调用 `create_rewritten_batch` 时，将 `dataset_id`、`item_ids` 或 `query_params` 传入，由服务层构造 `create_params` 并写入批次表。

---

## 4. 模型与仓储实现

### 4.1 模型文件

**路径**：`backend/infrastructure/database/models/rewritten_batch.py`

```python
"""Rewritten 批次模型。用于集中管理 rewritten 批次的 batch_code 及元数据。"""
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, generate_ulid

PIPELINE_TABLE_PREFIX = "pipeline_"

class RewrittenBatchRecord(Base):
    """Rewritten 批次记录"""

    __tablename__ = f"{PIPELINE_TABLE_PREFIX}rewritten_batches"

    id = Column(String(50), primary_key=True, index=True, default=generate_ulid, comment="ULID")
    batch_code = Column(String(100), nullable=False, unique=True, index=True, comment="批次编码")
    total_count = Column(Integer, nullable=False, comment="本批次数据项总量")
    create_params = Column(JSONB, nullable=True, comment="创建参数（JSON，含 dataset_id/dataset_ids 等）")
    status = Column(String(20), nullable=True, comment="批次级状态（可选）")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=sql_func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=sql_func.now(), comment="更新时间")
```

### 4.2 仓储文件

**路径**：`backend/infrastructure/database/repository/rewritten_batch_repository.py`

需提供：

- `create(batch_code, total_count, create_params=None, status=None)`：创建批次记录。
- `get_by_batch_code(batch_code)`：按 batch_code 查询单条。
- `get_list(limit, offset)`：分页查询批次列表；后续可按 `create_params->>'dataset_id'` 或 JSON 条件筛选，供 UI 使用。

### 4.3 数据库迁移

新增表 `pipeline_rewritten_batches`，按上述字段创建。若使用 Alembic，需生成对应 migration 脚本。

---

## 5. 与 data_items_rewritten 的关系

- `pipeline_data_items_rewritten.batch_code` 与 `pipeline_rewritten_batches.batch_code` 逻辑关联，通过 batch_code 可关联批次元数据。
- 初期可不建外键，保持灵活性；若需强约束，可考虑在 rewritten 表增加 `batch_id` 引用 `rewritten_batches.id`，与现有 `batch_code` 并存或替代。

---

## 6. rewritten_service 调用点变更

### 6.1 create_rewritten_batch 伪代码

```python
async def create_rewritten_batch(
    dataset_id: str,
    session: AsyncSession,
    *,
    item_ids: Optional[List[str]] = None,
    query_params: Optional[Dict[str, Any]] = None,
) -> RewrittenBatchCreateResult:
    # ... 查询 records，校验 ...
    if not records:
        return RewrittenBatchCreateResult(batch_code="", total=0)

    batch_code = datetime.now().strftime("%Y%m%d%H%M%S")
    total_count = len(records)
    create_params = _build_create_params(
        dataset_id=dataset_id,
        item_ids=item_ids,
        query_params=query_params,
    )

    batch_repo = RewrittenBatchRepository(session)
    await batch_repo.create(
        batch_code=batch_code,
        total_count=total_count,
        create_params=create_params,
    )

    rewritten_repo = DataItemsRewrittenRepository(session)
    created = await rewritten_repo.create_init_batch(
        records=records,
        batch_code=batch_code,
        dataset_id=dataset_id,
    )

    return RewrittenBatchCreateResult(batch_code=batch_code, total=created)
```

### 6.2 事务边界

批次表与 rewritten 表的写入应在同一 `session` 中完成，由 API 层的 `session.commit()` 统一提交，保证要么全部成功，要么全部回滚。

---

## 7. 后续 UI 扩展方向

批次表建立后，可支持：

1. **批次列表**：展示批次列表，含 batch_code、total_count、created_at、create_params 摘要；可按 `create_params->>'dataset_id'` 筛选。
2. **进度统计**：通过 batch_code 关联 `pipeline_data_items_rewritten`，统计 init/processing/success/failed 数量，展示执行进度。
3. **参数回放**：从 create_params 中读取 dataset_id、item_ids 或 query_params，支持「按相同条件再次创建」或「查看创建条件」。
4. **批次状态**：若引入 `status` 字段，可扩展为 pending/running/completed/failed 等，用于批次级状态展示。

---

## 8. 实施建议与顺序

| 序号 | 任务 | 说明 |
|------|------|------|
| 1 | 新建模型 `RewrittenBatchRecord` | `backend/infrastructure/database/models/rewritten_batch.py` |
| 2 | 新建仓储 `RewrittenBatchRepository` | `backend/infrastructure/database/repository/rewritten_batch_repository.py` |
| 3 | 数据库迁移 | 创建表 `pipeline_rewritten_batches` |
| 4 | 改造 `create_rewritten_batch` | 新增批次表写入逻辑，构建 create_params |
| 5 | 测试 | 覆盖批次创建、create_params 正确性、事务回滚 |

---

## 9. 附录：create_params 示例

### 9.1 按 item_ids 创建

请求：`{ "dataset_id": "ds001", "item_ids": ["id1", "id2", "id3"] }`

存储：

```json
{
  "dataset_id": "ds001",
  "mode": "item_ids",
  "item_ids": ["id1", "id2", "id3"]
}
```

### 9.2 按 query_params 创建

请求：`{ "dataset_id": "ds001", "query_params": { "status": 1, "keyword": "血压" } }`

存储：

```json
{
  "dataset_id": "ds001",
  "mode": "query_params",
  "query_params": {
    "status": 1,
    "keyword": "血压"
  }
}
```

### 9.3 空条件（全量）

请求：`{ "dataset_id": "ds001", "query_params": {} }`

存储：

```json
{
  "dataset_id": "ds001",
  "mode": "query_params",
  "query_params": {}
}
```

---

## 10. 开发完成情况

| 序号 | 任务 | 状态 | 说明 |
|------|------|------|------|
| 1 | 新建模型 RewrittenBatchRecord | ✅ 已完成 | `backend/infrastructure/database/models/rewritten_batch.py` |
| 2 | 新建仓储 RewrittenBatchRepository | ✅ 已完成 | `backend/infrastructure/database/repository/rewritten_batch_repository.py` |
| 3 | 数据库迁移 | ✅ 已完成 | `alembic/versions/20260211_add_pipeline_rewritten_batches_table.py` |
| 4 | 改造 create_rewritten_batch | ✅ 已完成 | 新增 _build_create_params、批次表写入逻辑 |
| 5 | 测试 | ✅ 已完成 | `cursor_test/test_rewritten_batch_create_params.py`，7 用例全部通过 |

---

*文档版本：1.0*  
*创建日期：2026-02-11*  
*开发完成日期：2026-02-11*
