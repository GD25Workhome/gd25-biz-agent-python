# pipeline_embedding_records 表与 Model/Repository 技术设计

## 1. 目标与范围

- **目标**：新增 Embedding 记录表 `pipeline_embedding_records`，并为其提供 SQLAlchemy Model 与 Repository，风格与现有 `backend/infrastructure/database/models/batch` 及 `repository/batch` 保持一致。
- **范围**：仅表结构、Model、Repository 及目录与包导出、迁移脚本；不包含API、业务编排（后续按需补充）。

## 2. 需求来源

- **文档**：`doc/总体设计规划/数据归档-schema/step3-数据embedding.md`
- **表名**：物理表名为 `pipeline_embedding_records`。前缀为 `pipeline_`，业务表名为 `embedding_records`；不使用 gd2502_ 前缀。Model 中 `__tablename__ = "pipeline_embedding_records"`。

## 3. 表结构设计

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | String(50) | PK, 默认 ULID | 主键，与 batch 一致使用 UlidIdMixin |
| version | Integer | NOT NULL, 默认 0 | 版本号，审计用 |
| is_deleted | Boolean | NOT NULL, 默认 False | 软删标记 |
| create_time | DateTime(TZ) | NOT NULL, 默认 now() | 创建时间 |
| update_time | DateTime(TZ) | NULL | 更新时间 |
| embedding_str | Text | 可空 | 用于生成 embedding 的文本 |
| embedding_value | Vector(2048) / Text | 可空 | Embedding 向量（2048 维）；无 pgvector 时退化为 Text |
| embedding_type | String(50) | 可空 | 类型：Q（仅提问）、QA（提问+回答） |
| is_published | Boolean | NOT NULL, 默认 False | 是否发布 |
| type | String(64) | 可空 | 主分类 |
| sub_type | String(64) | 可空 | 子分类（业务上若为空可用主分类填充） |
| metadata | JSON | 可空 | 扩展元数据 |

- **审计与主键**：与 batch 一致，采用 `UlidIdMixin` + `AuditFieldsMixin`（见 `backend/infrastructure/database/base`），保证 id/version/is_deleted/create_time/update_time 行为一致。
- **向量列**：与现有 `embedding_record.py` 一致，使用 `pgvector.sqlalchemy.Vector(2048)`；若未安装 pgvector 则列为 `Text` 并打警告（仅开发/兼容用，生产建议安装 pgvector）。

## 4. 目录与包结构

- **Model**：新建目录 `backend/infrastructure/database/models/pipeline/`，表对应模型放在此目录下。
  - 建议文件名：`pipeline_embedding_record.py`（单条记录模型）。
  - 包内需提供 `__init__.py`，导出该 Model（如 `PipelineEmbeddingRecord`）。
- **Repository**：新建目录 `backend/infrastructure/database/repository/pipeline/`，表对应仓储放在此目录下。
  - 建议文件名：`pipeline_embedding_record_repository.py`。
  - 包内需提供 `__init__.py`，导出该 Repository（如 `PipelineEmbeddingRecordRepository`）。
- **上层注册**：在 `backend/infrastructure/database/models/__init__.py` 与 `repository/__init__.py` 中从 pipeline 子包导入并加入 `__all__`，以便业务层统一从 infrastructure 使用。

## 5. Model 设计要点（对齐 batch 风格）

- **Mixin 拆分**：业务字段放入 `PipelineEmbeddingRecordBusinessMixin`，主键与审计字段通过 `UlidIdMixin`、`AuditFieldsMixin` 混入，与 `BatchJobRecord` / `BatchTaskRecord` 一致。
- **类名**：记录类命名为 `PipelineEmbeddingRecordRecord` 或 `PipelineEmbeddingRecord`（与现有 batch 的 `BatchJobRecord` 命名风格二选一，建议 `PipelineEmbeddingRecordRecord` 与 batch 的 `*Record` 一致）。
- **表名**：`__tablename__ = "pipeline_embedding_records"`（前缀 pipeline_，业务名 embedding_records，不使用 gd2502_）。
- **文档注释**：文件头注明设计文档为本技术设计文档路径（如 `cursor_docs/022801-pipeline_embedding_records表与model-repository技术设计.md`）。
- **__repr__**：实现简洁的 `__repr__`，便于日志与调试。

## 6. Repository 设计要点（对齐 batch 风格）

- **基类**：继承 `AuditBaseRepository[PipelineEmbeddingRecordRecord]`，与 `BatchJobRepository` / `BatchTaskRepository` 一致，自动享受按 id 查询过滤软删、create 时填充 id/version/is_deleted/create_time、update 时自增 version 与 update_time、delete 软删等行为。
- **构造函数**：`__init__(self, session: AsyncSession)`，内部调用 `super().__init__(session, PipelineEmbeddingRecordRecord)`。
- **方法建议**：
  - `create(...)`：显式参数对应业务字段（embedding_str、embedding_value、embedding_type、is_published、type、sub_type、metadata），其余用 `**kwargs` 传入；审计字段由基类 `create` 处理。
  - `get_by_id` / `get_all`：直接使用基类实现（已过滤 is_deleted）。
  - `get_list(limit, offset, type=None, sub_type=None, is_published=None)`：分页列表，按 type、sub_type、is_published 可选过滤，按 create_time 倒序。
- **类型与注释**：方法带完整类型注解与简体中文文档字符串；文件头注明设计文档路径。

## 7. 依赖与兼容

- **pgvector**：与 `embedding_record.py` 相同，在 Model 内 `try/except ImportError` 引入 `Vector`，无则退化为 `Text` 并 `warnings.warn`。
- **Base/Mixin**：仅依赖现有 `backend.infrastructure.database.base`（Base、UlidIdMixin、AuditFieldsMixin）与 `repository.base.AuditBaseRepository`，不新增第三方依赖。

## 8. 实施顺序建议

1. 在 `models/pipeline/` 下新增 `pipeline_embedding_record.py` 及 `__init__.py`。
2. 在 `repository/pipeline/` 下新增 `pipeline_embedding_record_repository.py` 及 `__init__.py`。
3. 在 `models/__init__.py` 与 `repository/__init__.py` 中注册 pipeline 子包的导出。
4. （可选）编写 Alembic 迁移生成 `pipeline_embedding_records` 表。
5. （可选）在 cursor_test 下为 Model 与 Repository 编写基础单测（创建、get_by_id、get_list 过滤）。

## 9. 与现有 embedding_record 的区别

- **embedding_record**：现有表，字段较多（如 scene_summary、optimization_question、message_id、trace_id、generation_status 等），无审计 Mixin（自建 id/version/created_at/updated_at）。
- **pipeline_embedding_records**：本设计表，字段精简为 step3 规定的 embedding_str、embedding_value、embedding_type、is_published、type、sub_type、metadata，并统一使用 UlidIdMixin + AuditFieldsMixin，与 batch 风格一致，便于后续与批次任务、数据清洗 pipeline 一起维护与扩展。

---

## 10. 完成情况

| 序号 | 项 | 状态 | 说明 |
|------|----|------|------|
| 1 | models/pipeline/pipeline_embedding_record.py | 已完成 | 含 PipelineEmbeddingRecordBusinessMixin、PipelineEmbeddingRecordRecord，表名 `pipeline_embedding_records`（前缀 pipeline_，业务名 embedding_records），embedding_value 支持 pgvector/Text 退化 |
| 2 | models/pipeline/__init__.py | 已完成 | 导出 PipelineEmbeddingRecordRecord |
| 3 | repository/pipeline/pipeline_embedding_record_repository.py | 已完成 | create、get_list(type_, sub_type, is_published) 等 |
| 4 | repository/pipeline/__init__.py | 已完成 | 导出 PipelineEmbeddingRecordRepository |
| 5 | models/__init__.py、repository/__init__.py 注册 | 已完成 | 已加入 pipeline 子包导出 |
| 6 | Alembic 迁移 | 已完成 | 20260228a001，创建 pipeline_embedding_records 表 |
| 7 | 单测 | 未要求 | 设计文档未要求编写测试用例，未实现 |

**说明**：Model 中主分类、元数据字段因与 Python 内置/常用名冲突，映射为 `type_`、`metadata_`，对应数据库列名仍为 `type`、`metadata`。

---

**文档版本**：v1  
**日期**：2026-02-28  
**关联**：`doc/总体设计规划/数据归档-schema/step3-数据embedding.md`
