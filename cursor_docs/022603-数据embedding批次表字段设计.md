# 数据 Embedding 批次表字段设计（待 Check）

基于 `doc/总体设计规划/数据归档-schema/step3-数据embedding.md` 中 ER 设计，整理表名与字段，便于评审。

---

## 1. 批次表：`batch_job`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | VARCHAR(50) | 主键（ULID，与现有模型一致，参见 `RewrittenBatchRecord.id` / `DataItemsRewrittenRecord.id`） |
| version | INT | 版本号（乐观锁） |
| is_deleted | BOOLEAN | 软删标记 |
| create_time | TIMESTAMP | 创建时间 |
| update_time | TIMESTAMP | 更新时间 |
| code | VARCHAR(64) | 批次编码，唯一 |
| total_count | INT | 总数（本批次待 embedding 条数） |
| query_params | JSON | 查询参数（如筛选条件、分页等） |

---

## 2. 子任务表：`batch_task`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | VARCHAR(50) | 主键（ULID，与现有模型一致，参见 `RewrittenBatchRecord.id` / `DataItemsRewrittenRecord.id`） |
| version | INT | 版本号（乐观锁） |
| is_deleted | BOOLEAN | 软删标记 |
| create_time | TIMESTAMP | 创建时间 |
| update_time | TIMESTAMP | 更新时间 |
| job_id | VARCHAR(50) | 关联批次表 `batch_job.id` |
| source_table_id | VARCHAR(50) | 来源表 ID（业务主键或来源系统 ID） |
| source_table_name | VARCHAR(128) | 来源表名（如 pipeline_data_items_rewritten） |
| status | VARCHAR(32) | 状态（如 pending/running/success/failed） |
| runtime_params | JSON | 运行时参数 |
| redundant_key | VARCHAR(256) | 冗余 key（去重/幂等用） |
| execution_result | TEXT | 执行返回结果 |
| execution_error_message | TEXT | 执行失败信息（含异常堆栈） |
| execution_return_key | VARCHAR(256) | 执行返回标识 key |

---

## 表名汇总

| 设计项 | 表名 |
|--------|------|
| 批次表 | `batch_job` |
| 子任务表 | `batch_task` |

---

## models 层代码改造

将公共字段拆成两个 Mixin（UlidIdMixin、AuditFieldsMixin），业务字段放入每表独立的业务 Mixin；模型类仅声明表名、不定义 Column。不修改现有 `Base` 与已有模型。继承顺序固定为 **UlidIdMixin → 业务 Mixin → AuditFieldsMixin → Base**，以保证 Alembic autogenerate 生成的建表语句中字段顺序为：**id 在前、业务在中间、审计在最后**（SQLAlchemy 按 MRO 收集列顺序）。

### 1. 公共 Mixin 定义与放置位置

- **UlidIdMixin**：仅主键 `id`（VARCHAR(50)、ULID、primary_key、index），与现有各表 id 一致。
- **AuditFieldsMixin**：审计与软删字段 `version`、`is_deleted`、`create_time`、`update_time`（类型与上文表设计一致）。

将上述两个 Mixin 定义在 `backend/infrastructure/database/base.py` 中（与 `Base`、`generate_ulid` 同文件）。

### 2. 业务 Mixin 与模型类

- **批次表**：定义 `BatchJobBusinessMixin`，仅包含业务列 `code`、`total_count`、`query_params`。模型类 `BatchJobRecord` 只设置 `__tablename__ = "batch_job"`，不定义任何 Column。
- **子任务表**：定义 `BatchTaskBusinessMixin`，仅包含业务列 `job_id`、`source_table_id`、`source_table_name`、`status`、`runtime_params`、`redundant_key`、`execution_result`、`execution_error_message`、`execution_return_key`。模型类 `BatchTaskRecord` 只设置 `__tablename__ = "batch_task"`，不定义任何 Column。

两张表对应两个 py 文件：`batch_job.py`（含 BatchJobBusinessMixin 与 BatchJobRecord）、`batch_task.py`（含 BatchTaskBusinessMixin 与 BatchTaskRecord）。文件统一放在 `backend/infrastructure/database/models/batch/` 下（新建 batch 目录）。

### 3. 继承顺序与最终类声明

继承顺序必须为：**UlidIdMixin → 业务 Mixin → AuditFieldsMixin → Base**。这样 MRO 收集到的列顺序为：id → 业务列 → 审计列。

- **批次表**：`class BatchJobRecord(UlidIdMixin, BatchJobBusinessMixin, AuditFieldsMixin, Base)`
- **子任务表**：`class BatchTaskRecord(UlidIdMixin, BatchTaskBusinessMixin, AuditFieldsMixin, Base)`

### 4. 与表设计、autogenerate 列顺序对应关系

| 表设计字段（022603） | 来源 | 建表时列顺序 |
|----------------------|------|--------------|
| id                   | UlidIdMixin | 第 1 批 |
| code / total_count / query_params（或 job_id、source_* 等） | 各表 BusinessMixin | 第 2 批（中间） |
| version, is_deleted, create_time, update_time | AuditFieldsMixin | 第 3 批（最后） |

使用 `alembic revision --autogenerate` 时，生成的 `op.create_table(...)` 将按上述顺序输出列，满足「id 在前、业务在中间、审计在最后」。

---

## repository 层代码改造

在 `backend/infrastructure/database/repository/base.py` 中新增 `AuditBaseRepository(BaseRepository)`，将 id/version/is_deleted/create_time/update_time 的统一逻辑集中在此基类；batch 相关仓储继承 `AuditBaseRepository`，其余仓储继续使用 `BaseRepository`。batch 的仓储代码统一放在 **`backend/infrastructure/database/repository/batch/`** 下（新建 batch 子目录），如 `batch_job_repository.py`、`batch_task_repository.py`。

### 1. AuditBaseRepository 统一行为

| 项 | 行为 |
|----|------|
| **id** | 新增时若未传入 id，则使用 `generate_ulid()` 自动生成；若显式传入则使用传入值。 |
| **version** | 新增时默认 0；每次 `update(id, **kwargs)` 时在原有 version 基础上 +1（非乐观锁，仅自增）。 |
| **is_deleted** | 新增时默认 0；`delete(id)` 改为软删（update 为 1）；所有查询默认只查 `is_deleted=0`。 |
| **create_time** | 新增时使用系统当前时间赋值。 |
| **update_time** | 新增时不主动设置；每次 `update(id, **kwargs)` 时使用系统当前时间赋值。 |

- **放置**：`AuditBaseRepository` 与 `BaseRepository` 同文件 `base.py`，暂不拆分为独立文件。
- **约定**：使用 AuditBaseRepository 的 Model 必须具有上述五列；时间按项目约定使用系统当前时间（如 `datetime.now()`）。

### 2. 方法要点（create / update / delete / get）

- **create**：未传则补 id（generate_ulid）、version=0、is_deleted=0、create_time=当前时间；然后调用 `super().create(**kwargs)`。
- **update**：先 `get_by_id(id)` 取实例，若存在则 `kwargs["version"] = instance.version + 1`、`kwargs["update_time"] = 当前时间`，再对 instance setattr 并 flush；不存在返回 None。
- **delete**：不物理删，改为 `update(id, is_deleted=1)`（软删）。
- **get_by_id / get_all**：在 Base 的 select 上增加条件 `self.model.is_deleted == 0`；若需查已删可后续提供 `get_by_id_include_deleted` 等单独方法。

### 3. 未删条件与子类约定

- AuditBaseRepository 提供受保护方法 **`_not_deleted_criterion()`**，返回 `self.model.is_deleted == 0`，供内部 get_by_id/get_all 及子类复用。
- 子类自定义方法中凡自行拼 `select(self.model).where(...)` 的，**必须**在 where 中加上 `self._not_deleted_criterion()`（或等价条件），否则会查出已删数据；子类不得重写 `_not_deleted_criterion()`。

### 4. batch 仓储与目录

- **BatchJobRepository**：继承 `AuditBaseRepository[BatchJobRecord]`，放在 `repository/batch/batch_job_repository.py`。
- **BatchTaskRepository**：继承 `AuditBaseRepository[BatchTaskRecord]`，放在 `repository/batch/batch_task_repository.py`。
- 在 `repository/__init__.py` 中按需导出 BatchJobRepository、BatchTaskRepository（或从 `repository.batch` 子包导出）。详细实现与单测见 `cursor_docs/022605-BaseRepository审计逻辑改造方案-路线B.md`。

---

## 说明与待确认点

1. **基础字段**：两张表均包含 `id`、`version`、`is_deleted`、`create_time`、`update_time`。
2. **表名**：均以 `batch` 开头，与“批次任务模块”语义一致。
3. **子任务与批次**：`batch_task.job_id` 关联 `batch_job.id`，便于按批次查询与统计。
4. **主键与关联**：`id`、`job_id` 与现有模型一致，使用 VARCHAR(50) 存 ULID（参见 `backend/infrastructure/database/models/rewritten_batch.py`、`data_items_rewritten.py`）。`query_params`/`runtime_params`/`execution_result` 用 JSONB 还是 TEXT 可按项目规范统一。
5. **状态枚举**：`batch_task.status` 建议在文档或代码中约定枚举值（如 0=pending, 1=running, 2=success, -1=failed）。

请 Check 表名、字段名与类型是否符合项目规范与后续扩展需求。

---

## 实现完成情况

- **base.py**：已添加 `UlidIdMixin`、`AuditFieldsMixin`（`backend/infrastructure/database/base.py`）。
- **models 层**：已新建 `backend/infrastructure/database/models/batch/`，内含 `batch_job.py`（BatchJobBusinessMixin、BatchJobRecord）、`batch_task.py`（BatchTaskBusinessMixin、BatchTaskRecord）、`__init__.py`；已由 `models/__init__.py` 导出。
- **repository 层**：已在 `repository/base.py` 中新增 `AuditBaseRepository`（含 create/update/delete/get_by_id/get_all 及 `_not_deleted_criterion()`）；已新建 `repository/batch/`，内含 `batch_job_repository.py`（BatchJobRepository）、`batch_task_repository.py`（BatchTaskRepository）、`__init__.py`；已由 `repository/__init__.py` 导出。
- **Alembic**：已生成迁移 `alembic/versions/92b2c1042946_add_batch_job_and_batch_task_tables.py`，仅包含 batch_job、batch_task 的建表与索引（已剔除 autogenerate 产生的无关变更）。执行 `alembic upgrade head` 可建表。
- **测试**：已新增 `cursor_test/test_batch_models_and_repository.py`（表名与列校验、AuditBaseRepository 及 batch 仓储继承关系），运行 `pytest cursor_test/test_batch_models_and_repository.py -v` 已通过。
