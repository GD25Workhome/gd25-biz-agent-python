# BaseRepository 审计逻辑改造方案（路线 B）

采用**路线 B**：新增 `AuditBaseRepository(BaseRepository)`，将 id/version/is_deleted/create_time/update_time 的统一逻辑集中在此基类；仅「带审计字段」的仓储（如 batch_job、batch_task）继承 `AuditBaseRepository`，其余仓储继续继承 `BaseRepository`，现有 Base 与无审计表不受影响。本文档为详细改造方案，供审阅。

---

## 1. 目标行为（统一逻辑）

| 项 | 行为 |
|----|------|
| **id** | 新增时若未传入 id，则使用 `generate_ulid()` 自动生成；若调用方显式传入 id，则使用传入值。 |
| **version** | 新增时默认 0；每次调用 `update(id, **kwargs)` 时，在原有 version 基础上 +1。 |
| **is_deleted** | 新增时默认 0；`delete(id)` 时改为 1（软删）；所有查询方法默认只查 `is_deleted=0`，如需查已删/全部需走单独接口或参数。 |
| **create_time** | 新增时使用系统当前时间赋值。 |
| **update_time** | 每次 `update(id, **kwargs)` 时使用当前系统时间赋值。 |

上述逻辑**仅对继承 AuditBaseRepository 且模型具备对应列的仓储生效**；继承 BaseRepository 的仓储行为不变。

---

## 2. 新增类与放置位置

- **类名**：`AuditBaseRepository(Generic[ModelType])`，继承自 `BaseRepository[ModelType]`。
- **放置**：与 `BaseRepository` 同文件 `backend/infrastructure/database/repository/base.py`，暂不拆分为独立 `audit_base.py`。

---

## 3. AuditBaseRepository 改造要点

### 3.1 前置约定

- **模型约定**：使用 AuditBaseRepository 的 Model 必须具有列：`id`、`version`、`is_deleted`、`create_time`、`update_time`（与 022603 表设计一致）。不在 AuditBaseRepository 内做「有无该列」的兼容判断，避免与无审计表混用。
- **时间**：统一使用系统当前时间赋值（如 `datetime.now()` 或 `datetime.now(timezone.utc)`，按项目约定选用即可）。

### 3.2 create(**kwargs)

- 若 `kwargs` 中未包含 `"id"`，则 `kwargs["id"] = generate_ulid()`。
- 若未传 `version`，则 `kwargs["version"] = 0`。
- 若未传 `is_deleted`，则 `kwargs["is_deleted"] = 0`（或 `False`，与列类型一致）。
- 若未传 `create_time`，则 `kwargs["create_time"] = 当前时间`。
- 新增时 `update_time` 不主动设置（由 DB 或业务按需处理）。
- 然后调用 `super().create(**kwargs)`（即 BaseRepository.create），由基类完成 `self.model(**kwargs)`、add、flush。

### 3.3 update(id: str, **kwargs)

- 先调用 `get_by_id(id)` 获取实例（注意：AuditBaseRepository 的 get_by_id 已带 is_deleted=0，故拿到的必是未删记录）。
- 若实例不存在，返回 None。
- 若实例存在：  
  - 将 `kwargs["version"] = getattr(instance, "version", 0) + 1`；  
  - 将 `kwargs["update_time"] = 当前时间`。  
- 再调用 `super().update(id, **kwargs)` 或直接对 instance 做 setattr 并 flush。注意：不要再次通过 get_by_id 取实例（避免重复逻辑），用已取到的 instance 即可。

### 3.4 delete(id: str)

- 不调用 `session.delete(instance)`，改为调用 `update(id, is_deleted=1)`（或 `True`，与列类型一致），即软删。
- 返回 True/False 可与 update 的返回值一致（如 update 成功则返回 True）。

### 3.5 get_by_id(id: str)

- 在 BaseRepository 的 `select(self.model).where(self.model.id == id)` 基础上，增加条件 `self.model.is_deleted == 0`。
- 若需「按 id 查且包含已删」，可提供单独方法如 `get_by_id_include_deleted(id)`，或增加参数 `include_deleted: bool = False`，审阅时可二选一。

### 3.6 get_all(limit, offset)

- 在 BaseRepository 的 select 上增加条件 `self.model.is_deleted == 0`。
- 若需「查全部含已删」，可提供 `get_all_include_deleted(limit, offset)` 或参数 `include_deleted=False`。

### 3.7 未删条件与子类自定义查询

#### 3.7.1 受保护方法 `_not_deleted_criterion()`

- **用途**：统一提供「未删除」的查询条件，供 AuditBaseRepository 内部的 get_by_id、get_all 以及子类自定义查询复用，避免多处手写 `self.model.is_deleted == 0`。
- **方法名**：`_not_deleted_criterion()`（单下划线，表示受保护、供子类使用）。
- **返回值**：SQLAlchemy 条件表达式，即 `self.model.is_deleted == 0`（若 DB 列为 BOOLEAN 且用 False 表示未删，则可为 `self.model.is_deleted == False`，与模型定义一致即可）。
- **定义位置**：AuditBaseRepository 内实现，子类直接调用。

#### 3.7.2 在 AuditBaseRepository 内部的使用

- **get_by_id(id)**：查询条件为 `self.model.id == id` 与 `self._not_deleted_criterion()` 的 and 组合。
- **get_all(limit, offset)**：在 select 上增加 where 条件 `self._not_deleted_criterion()`。
- 若后续提供「含已删」的查询（如 get_by_id_include_deleted、get_all_include_deleted），则这些方法**不再**附加 `_not_deleted_criterion()`，与默认行为区分开。

#### 3.7.3 子类自定义查询的约定

- 凡继承 AuditBaseRepository 的子类，在自定义方法中自行拼 `select(self.model).where(...)` 时，**必须**在 where 中加上未删条件，否则会查出已删数据。
- **推荐写法**：在拼条件时统一使用 `self._not_deleted_criterion()`，例如：
  - `.where(self.model.job_id == job_id, self._not_deleted_criterion())`
  - 或 `.where(and_(..., self._not_deleted_criterion()))`
- 子类**不得**重写 `_not_deleted_criterion()`，以保持「未删」语义一致；若某子类确有「默认查已删」的特殊需求，可单独提供方法并在文档中说明。

---

## 4. 现有 BaseRepository 是否修改

- **不修改** BaseRepository 的 create/update/delete/get_by_id/get_all 实现，保持对现有无审计表的行为不变。
- 仅**新增** AuditBaseRepository，并在文档/注释中说明：带审计字段的仓储继承 AuditBaseRepository，其余继承 BaseRepository。

---

## 5. 使用方改造（batch 仓储）

- **BatchJobRepository**：由 `BaseRepository[BatchJobRecord]` 改为 `AuditBaseRepository[BatchJobRecord]`，`__init__` 仍为 `super().__init__(session, BatchJobRecord)`。
- **BatchTaskRepository**：由 `BaseRepository[BatchTaskRecord]` 改为 `AuditBaseRepository[BatchTaskRecord]`，同上。
- 若 BatchJobRepository / BatchTaskRepository 有自定义的 `get_list`、`get_by_code`、`get_tasks_by_job_id` 等，在构造 `select(...).where(...)` 时需加上 `self._not_deleted_criterion()`（或直接写 `self.model.is_deleted == 0`）。

---

## 6. 影响点与风险

| 项 | 说明 |
|----|------|
| **模型列名** | AuditBaseRepository 假定列名为 id、version、is_deleted、create_time、update_time；若 022603 最终定为 create_time/update_time，与现有部分表 created_at/updated_at 不一致，仅 batch 表使用，无冲突。 |
| **version 与并发** | 当前方案为「每次 update 则 version+1」，未做乐观锁校验（如 WHERE version=旧值）；若后续需要乐观锁，可在 update 时加上 version 条件并在 rowcount=0 时抛错或返回失败。审阅阶段可先不做，仅做自增。 |
| **软删与唯一约束** | 若表上有唯一约束（如 batch_job.code），软删后该行仍在，同一 code 无法再插入；若业务允许「删后复用 code」，需在唯一约束或业务上考虑（如唯一约束改为 (code, is_deleted) 或仅对 is_deleted=0 建部分唯一索引）。 |
| **时间函数** | 使用系统当前时间（如 `datetime.now()`），可按项目约定统一封装便于测试与一致性。 |

---

## 7. 实施顺序建议

1. 在 `backend/infrastructure/database/repository/base.py` 中实现 AuditBaseRepository，并在 `repository/__init__.py` 中一并导出。
2. 实现 AuditBaseRepository：先实现 `_not_deleted_criterion()`、再 create（id/version/is_deleted/create_time，update_time 新增时不设置）、再 update（version+1、update_time）、再 delete（软删）、再 get_by_id/get_all（加 is_deleted=0）。
3. 编写单测：针对 AuditBaseRepository 的 create/update/delete/get_by_id/get_all 及「不传 id 则生成」「update 后 version 与 update_time 变化」「delete 后 get_by_id 不可见」等。
4. 在 batch 模型与 migration 就绪后，将 BatchJobRepository、BatchTaskRepository 改为继承 AuditBaseRepository，并检查其自定义查询是否均加上未删条件。
5. 在 022603 或本方案文档中补充说明：带审计字段的新表，其仓储应继承 AuditBaseRepository。

---

## 8. 审阅检查清单

- [ ] AuditBaseRepository 已与 BaseRepository 同置于 `base.py` 并在 `repository/__init__.py` 中导出。
- [ ] create/update/delete/get_by_id/get_all 行为是否符合上文 1～3 节描述。
- [ ] 子类自定义查询是否约定使用 `_not_deleted_criterion()` 或显式 is_deleted=0。
- [ ] 是否需要 get_by_id_include_deleted / get_all_include_deleted（或 include_deleted 参数）以满足运维/排查已删数据需求。
- [ ] 时间是否按项目约定使用系统当前时间。
- [ ] version 是否暂不做乐观锁校验，仅自增。
- [ ] 软删与唯一约束（如 code）的兼容是否在表设计或后续迭代中考虑。

请审阅后确认是否按本方案实施；若有调整点（如列名、是否需要乐观锁、是否提供 include_deleted），可在文档中批注或补充一节「审阅结论与变更」。
