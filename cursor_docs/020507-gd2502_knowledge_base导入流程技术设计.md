# gd2502_knowledge_base 导入流程技术设计文档

**文档编号**：020507  
**创建日期**：2025-02-05  
**需求来源**：scripts/import_to_datasets/QA_case/QA的case梳理思路.md  
**关联文档**：cursor_docs/020402-数据导入流程技术设计.md、cursor_docs/020506-unique_key在导入流程中的生成与传递设计.md  

---

## 1. 概述

### 1.1 目标

在 `backend/pipeline` 数据清洗流程中，新增一条从数据库表 `gd2502_knowledge_base` 读取数据、经清洗后写入 DataSets 的导入流程。该流程遵循现有「读取器 → 清洗器 → 入库执行器」三阶段设计原则。

### 1.2 数据来源与业务背景

- **表**：`gd2502_knowledge_base`（KnowledgeBaseRecord ORM）
- **数据来源**：产品 PRD 数据提取，经 `create_rag_agent` 流程清洗后入库
- **目标**：将知识库表数据转换为 DataSets 标准格式，供 Langfuse 评估与后续使用

### 1.3 流程架构（三阶段）

```
┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
│  PG 数据库读取器          │ ──► │  KnowledgeBase 清洗器    │ ──► │  入库执行器              │
│  (gd2502_knowledge_base) │     │  (impl/knowledge_base.py)│     │  (DatasetItemWriter)    │
└─────────────────────────┘     └─────────────────────────┘     └─────────────────────────┘
         │                                │                                │
         ▼                                ▼                                ▼
    sourceType: pg                  cleaners.default               dataSetsId
    sourcePath.tableName            = "knowledge_base"             校验后写入
```

---

## 2. 数据源结构

### 2.1 表字段（gd2502_knowledge_base）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(50) | 主键（ULID），用于追溯源记录 |
| scene_summary | Text | 场景摘要：1～3 句自然语言，概括该案例的提问背景 |
| optimization_question | Text | 优化问题：从原文患者提问中总结的完整、清晰问题 |
| reply_example_or_rule | Text | 回复案例 or 规则：回复案例；或规则（需加「回复规则：」前缀） |
| scene_category | String(500) | 场景大类 |
| input_tags | JSONB | 输入侧标签数组 |
| response_tags | JSONB | 回复侧标签数组 |
| raw_material_full_text | Text | 原始资料-全量文字 |
| source_meta | JSONB | 来源信息，如 `{"source_file": "相对路径"}`，可为空 |
| ... | ... | 其它字段（本流程不涉及） |

### 2.2 业务规则（来自 QA 文档）

- **reply_example_or_rule**：若能直接提取回复案例，则存回复案例；否则存规则，并在规则前加「回复规则：」前缀
- **input**：`optimization_question` 作为患者发言（当前消息）
- **output**：`reply_example_or_rule` 作为回复或回复规则；若以「回复规则：」开头，则需放入 `response_rule` 字段，并兼容「仅回复规则」的 schema

---

## 3. 三阶段详细设计

### 3.1 阶段一：PG 数据库读取器（readers）

#### 3.1.1 新增 PgReader

**文件**：`backend/pipeline/readers/pg_reader.py`

**职责**：根据配置从 PostgreSQL 表读取数据，输出为 `(logical_name, DataFrame)` 的迭代。

**配置结构**（sourceType=pg 时）：

```json
{
  "sourceType": "pg",
  "sourcePath": {
    "tableName": "gd2502_knowledge_base"
  },
  "cleaners": {
    "default": "knowledge_base"
  },
  "dataSetsId": "01ARZ3NDEKTSV4RRFFQ69G5FAV"
}
```

**实现要点**：

- 使用 SQLAlchemy 异步会话执行 `SELECT * FROM gd2502_knowledge_base`（或通过 ORM 查询）
- 将查询结果转换为 `pd.DataFrame`
- **异步获取**：数据库查询为异步操作，需在 `iter_sheets()` 前完成数据拉取。建议 PgReader 提供 `async def fetch(session)` 方法，在 execute_import 中先调用 `await reader.fetch(session)`，将数据加载至内存；`iter_sheets()` 随后同步 yield `("default", df)`。或：扩展 BaseReader 支持 `async def iter_sheets_async()`，由 import_service 使用 `async for` 迭代（需同步修改 ExcelReader 以保持接口一致）。**首版建议**：PgReader 实现 `fetch(session)` + 同步 `iter_sheets()`，与现有 import_service 循环兼容。
- `iter_sheets()` 返回 `Iterator[Tuple[str, pd.DataFrame]]`，对单表场景 yield `("default", df)`，逻辑名用于匹配 `cleaners` 配置
- 若需支持多表，可扩展为 yield `(table_name, df)`，本设计首版仅单表

**BaseReader 兼容性**：

- `BaseReader.iter_sheets()` 返回 `(str, pd.DataFrame)`，PG 场景下第一项为逻辑分区名（如 `"default"`），与 Excel 的 sheet_name 语义一致，便于 import_service 复用 `cleaners.get(sheet_name) or cleaners.get("default")` 逻辑。

#### 3.1.2 读取器注册与分发

**文件**：`backend/pipeline/import_service.py`

**改造**：根据 `sourceType` 选择读取器，PG 时需先异步拉取数据：

```python
if source_type == "excel":
    reader = ExcelReader(meta)
elif source_type == "pg":
    reader = PgReader(meta)
    await reader.fetch(session)  # 异步拉取表数据至内存
else:
    raise UnsupportedSourceTypeError(source_type)
```

---

### 3.2 阶段二：KnowledgeBase 清洗器（cleaners）

#### 3.2.1 新增 KnowledgeBaseCleaner

**文件**：`backend/pipeline/cleaners/impl/knowledge_base.py`

**职责**：将 DataFrame 行（对应 KnowledgeBaseRecord 的一行）清洗为 `CanonicalItem`，并设置 `unique_key`。

**输入**：`row` 为表的一行，`df` 为全表 DataFrame（列名与表字段一致）。

**输出**：`List[CanonicalItem]`，本清洗器 1 行 → 1 条。

**字段映射**：

| 表字段 | CanonicalItem 字段 | 说明 |
|--------|-------------------|------|
| optimization_question | current_msg | 患者发言 |
| （无） | history_messages | 空列表 `[]` |
| reply_example_or_rule | response_message 或 response_rule | 见 3.2.2 |
| scene_summary, scene_category, input_tags, response_tags, raw_material_full_text | context["original_extract"] | 见 3.2.3 |
| id, source_meta | step1_metadata | 见 3.2.6 |

#### 3.2.2 reply_example_or_rule 分支逻辑

- **若** `reply_example_or_rule` 以「回复规则：」开头：
  - 将**去掉前缀后的内容**存入 `CanonicalItem.response_rule`
  - `response_message` 置空字符串 `""`
- **否则**：
  - 将全文存入 `response_message`
  - `response_rule` 不设置（保持 None）

**设计原则**：通过扩展 CanonicalItem 的 `response_rule` 字段，由通用转换器 `canonical_to_dataset_item` 统一写入 output，主流程无需按 cleaner_key 分支。

#### 3.2.3 metadata 与 original_extract

清洗器将以下字段放入 `context["original_extract"]`，供转换层迁入 metadata：

| 字段 | 说明 |
|------|------|
| scene_summary | 场景摘要 |
| scene_category | 场景大类 |
| input_tags | 输入侧标签（JSONB，保持原结构） |
| response_tags | 回复侧标签（JSONB，保持原结构） |
| raw_material_full_text | 原始资料-全量文字 |

**说明**：当前 `canonical_to_dataset_item` 将 `item.context` 整体放入 `metadata.content_info.user_info`，故 `context["original_extract"]` 会落在 `metadata.content_info.user_info.original_extract`。若需 `metadata.original_extract` 根层级，需在实现时另行处理（如扩展转换器或 KnowledgeBase 专用逻辑）。

#### 3.2.4 unique_key 生成规则

**规则**：使用 MD5 算法，将以下三个字段用换行符 `\n` 连接成字符串，计算 MD5 作为 unique_key。

```
unique_key = md5(scene_summary + "\n" + optimization_question + "\n" + reply_example_or_rule)
```

**实现**：

```python
import hashlib

def _compute_unique_key(
    scene_summary: Optional[str],
    optimization_question: Optional[str],
    reply_example_or_rule: Optional[str],
) -> str:
    parts = [
        (scene_summary or "").strip(),
        (optimization_question or "").strip(),
        (reply_example_or_rule or "").strip(),
    ]
    content = "\n".join(parts)
    return hashlib.md5(content.encode("utf-8")).hexdigest()
```

**说明**：表内无天然唯一业务键，采用内容哈希保证去重与幂等；空字符串参与计算，避免不同空值产生相同 key。

#### 3.2.5 is_empty_row

- 若 `optimization_question` 与 `reply_example_or_rule` 均为空（或 None），则视为空行，跳过。

#### 3.2.6 step1_metadata：源表追溯信息

**目的**：将源 PG 表的 `id`、`source_meta` 作为独立字段存储，便于导入后追溯数据来源，不混入业务 context。

**CanonicalItem 扩展**（`backend/pipeline/cleaners/canonical.py`）：

- 新增字段：`step1_metadata: Optional[Dict[str, Any]] = None`
- 类型：`Dict[str, Any]`，可选，默认 None
- 语义：阶段一（读取）的元数据，由具备源表信息的清洗器（如 KnowledgeBaseCleaner）填充

**step1_metadata 结构**（KnowledgeBase 场景）：

```json
{
  "id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "source_meta": {
    "source_file": "cursor_docs/012802-QA场景独立记录/01-诊疗-场景1.md"
  }
}
```

| 键 | 类型 | 必填 | 说明 |
|----|------|------|------|
| id | string | 是 | 源表主键（gd2502_knowledge_base.id），ULID |
| source_meta | object \| null | 否 | 源表 source_meta 字段，JSONB 原样透传；可为 null |

**KnowledgeBaseCleaner 赋值逻辑**：

- 从 `row` 读取 `id`、`source_meta`（DataFrame 列名与表字段一致）
- 构造 `step1_metadata = {"id": row.get("id"), "source_meta": row.get("source_meta")}`
- `id`：必填，若缺失则 `step1_metadata["id"]` 为 None，建议记录 warning
- `source_meta`：JSONB 列，PgReader 转为 DataFrame 后通常为 `dict` 或 `None`；若为 JSON 字符串需解析后写入
- `source_meta` 为 None 时，`step1_metadata["source_meta"]` 为 `None`，写入 metadata 时 JSON 中为 `null`

**canonical_to_dataset_item 扩展**（`backend/pipeline/cleaners/canonical.py`）：

- 在构建 `item_metadata` 时，若 `item.step1_metadata` 非空，则 `item_metadata["step1_metadata"] = item.step1_metadata`
- 最终写入 `pipeline_data_sets_items.metadata`（JSONB 根层级）

**向后兼容**：Excel 等清洗器不设置 `step1_metadata`，保持 None，转换后 metadata 中无 `step1_metadata` 键，与现有行为一致。

**设计评审要点**：

| 项目 | 说明 |
|------|------|
| 与 original_extract 的关系 | `step1_metadata` 存源表追溯（id、source_meta），`original_extract` 存业务提取字段（scene_summary 等），职责分离 |
| metadata 最终结构 | `metadata.step1_metadata` 与 `metadata.content_info` 平级，均为 metadata 根层级键 |
| 扩展性 | 未来其它 PG 源清洗器也可填充 `step1_metadata`，结构可扩展（如增加 `table_name` 等） |

---

### 3.3 阶段三：转换与入库（canonical → writers）

#### 3.3.1 通用转换器扩展（无定制逻辑）

**设计原则**：主流程不按 cleaner_key 分支，所有清洗器统一使用 `canonical_to_dataset_item`。通过扩展 CanonicalItem 与通用转换器，实现 KnowledgeBase 等新场景的兼容。

**CanonicalItem 扩展**（`backend/pipeline/cleaners/canonical.py`）：

- 新增字段：`response_rule: Optional[str] = None`，与 `response_message` 二选一
- 新增字段：`step1_metadata: Optional[Dict[str, Any]] = None`，阶段一源表追溯信息（设计文档：020507）

**canonical_to_dataset_item 扩展**：

- output 增加：`"response_rule": item.response_rule or ""`
- metadata 增加：若 `item.step1_metadata` 非空，则 `item_metadata["step1_metadata"] = item.step1_metadata`

**转换规则**（通用，无需按清洗器分支）：

| 目标 | 来源 |
|------|------|
| **output.response_message** | item.response_message |
| **output.response_rule** | item.response_rule |
| **output.flow_msgs** | [] |
| **metadata.step1_metadata** | item.step1_metadata（若存在） |

**import_service**：无需改造，继续统一调用 `canonical_to_dataset_item(item)`。

#### 3.3.2 source 字段

PG 场景的 source 建议格式：`pg:gd2502_knowledge_base`，便于追溯数据来源。

---

## 4. 配置结构扩展

### 4.1 import_config.import_config（sourceType=pg）

```json
{
  "sourceType": "pg",
  "sourcePath": {
    "tableName": "gd2502_knowledge_base"
  },
  "cleaners": {
    "default": "knowledge_base"
  },
  "dataSetsId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "clearBeforeImport": false
}
```

### 4.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| sourceType | string | 是 | `pg` 表示数据库表 |
| sourcePath.tableName | string | 是 | 表名，如 `gd2502_knowledge_base` |
| cleaners.default | string | 是 | 清洗器 key，本流程为 `knowledge_base` |
| dataSetsId | string | 是 | 目标 DataSets ID |
| clearBeforeImport | boolean | 否 | 导入前是否清空目标 dataset 的 items |

**说明**：PG 单表场景无需 `sheetNames`，`cleaners` 仅需 `default`；若未来支持多表，可扩展 `cleaners` 为 `{"tableName": "knowledge_base"}` 形式。

---

## 5. 清洗器注册

**文件**：`backend/pipeline/cleaners/registry.py`

新增：

```python
from backend.pipeline.cleaners.impl.knowledge_base import KnowledgeBaseCleaner

_CLEANER_REGISTRY = {
    ...
    "knowledge_base": KnowledgeBaseCleaner,
}
```

---

## 6. 数据流与传递链路

```
PgReader.iter_sheets()
    → ("default", DataFrame)
        ↓
KnowledgeBaseCleaner.clean(row, df)
    → List[CanonicalItem]
        - current_msg = optimization_question
        - history_messages = []
        - response_message = 回复案例 或 ""
        - response_rule = 规则内容（仅当「回复规则：」开头，去掉前缀）
        - context["original_extract"] = { scene_summary, scene_category, input_tags, response_tags, raw_material_full_text }
        - step1_metadata = { id, source_meta }（源表追溯）
        - unique_key = md5(scene_summary + "\n" + optimization_question + "\n" + reply_example_or_rule)
        ↓
canonical_to_dataset_item(item)  # 通用转换，无分支
    → DatasetItemDto
        - input: { current_msg, history_messages }
        - output: { response_message, response_rule, flow_msgs }
        - metadata: content_info.user_info 含 original_extract；step1_metadata（若存在）
        ↓
writer.write_item(..., unique_key=item.unique_key)
    → pipeline_data_sets_items
```

---

## 7. 实现任务清单

### 7.1 第一阶段：PG 读取器

| 序号 | 任务 | 产出 |
|------|------|------|
| 1 | 实现 PgReader | readers/pg_reader.py |
| 2 | import_service 支持 sourceType=pg | import_service.py |

### 7.2 第二阶段：KnowledgeBase 清洗器与 CanonicalItem 扩展

| 序号 | 任务 | 产出 |
|------|------|------|
| 3 | CanonicalItem 增加 response_rule、step1_metadata；canonical_to_dataset_item 扩展 output.response_rule、metadata.step1_metadata | cleaners/canonical.py |
| 4 | 实现 KnowledgeBaseCleaner | cleaners/impl/knowledge_base.py |
| 5 | 注册 knowledge_base 清洗器 | cleaners/registry.py |

### 7.3 第三阶段：测试与文档

| 序号 | 任务 | 产出 |
|------|------|------|
| 7 | 单元测试 | cursor_test/pipeline/test_knowledge_base_import.py |
| 8 | 集成测试（可选） | 端到端导入验证 |

---

## 8. 风险与注意事项

| 项目 | 说明 |
|------|------|
| **output.response_rule 与 schema** | DataSets 的 output schema 需支持 `response_rule` 可选字段；若目标 DataSet 的 output_schema 未定义 response_rule，可能需在创建 DataSet 时扩展 schema，或与前端/Langfuse 约定 |
| **空值处理** | scene_summary、optimization_question、reply_example_or_rule 任一为空时，用空字符串参与 MD5，避免 key 冲突 |
| **JSONB 序列化** | input_tags、response_tags 为 JSONB，写入 metadata.original_extract 时保持 list 结构，不序列化为字符串 |
| **历史数据** | 本流程为新增，不影响现有 Excel 导入；PG 与 Excel 可共用同一 DatasetItemWriter |
| **事务与性能** | 大批量导入时，考虑分批 commit 或使用 bulk insert，避免长事务 |

---

## 9. 设计审查与遗漏检查

### 9.1 设计原则（通用化）

**用户方案**：不为主流程增加 cleaner_key 分支，通过扩展 CanonicalItem 与 `canonical_to_dataset_item` 实现通用支持。

**实现要点**：
- CanonicalItem 新增 `response_rule: Optional[str] = None`、`step1_metadata: Optional[Dict[str, Any]] = None`
- `canonical_to_dataset_item` 在 output 中增加 `response_rule` 赋值，在 metadata 中增加 `step1_metadata` 赋值（若存在）
- import_service 保持统一调用 `canonical_to_dataset_item`，无分支

**向后兼容**：现有清洗器（LSK、Sh1128 等）不设置 `response_rule`，output 中为 `""`；不设置 `original_extract` 时 metadata 无此键，行为与改造前一致。

### 9.2 已覆盖点

- [x] 三阶段架构（读取器 → 清洗器 → 入库执行器）
- [x] unique_key 生成（MD5 三字段拼接）
- [x] input/output/metadata 映射
- [x] reply_example_or_rule 分支（回复案例 vs 回复规则）
- [x] original_extract 存储
- [x] PG 读取器与 Excel 读取器并存
- [x] 通用 CanonicalItem 扩展（response_rule、step1_metadata），主流程无 cleaner_key 分支

### 9.3 潜在遗漏与建议

| 项目 | 说明 |
|------|------|
| **output_schema 兼容性** | 若目标 DataSet 的 output_schema 要求 `response_message` 必填，则「仅回复规则」场景可能违反 schema；建议在 DataSet 创建时允许 `response_message` 与 `response_rule` 二选一，或均设为可选 |
| **optimization_question 为 JSON 数组** | 表中 optimization_question 可能为 JSON 数组的序列化（见 insert_rag_data_func 的 _normalize_optimization_question）；若为 `'["q1","q2"]'` 字符串，清洗器需解析 JSON，取第一个元素作为 current_msg；若解析失败则原样使用。unique_key 计算时使用原始字符串，保证与入库时一致 |
| **id / source_meta** | 已通过 `step1_metadata` 设计覆盖，见 3.2.6 |

---

## 10. 附录

### 10.1 涉及文件清单

| 文件 | 变更类型 |
|------|----------|
| backend/pipeline/readers/pg_reader.py | 新建 |
| backend/pipeline/cleaners/canonical.py | 扩展 CanonicalItem.response_rule、step1_metadata；output.response_rule；metadata.step1_metadata |
| backend/pipeline/cleaners/impl/knowledge_base.py | 新建 |
| backend/pipeline/cleaners/registry.py | 注册 knowledge_base |
| backend/pipeline/import_service.py | 支持 sourceType=pg、PgReader.fetch |
| cursor_test/pipeline/test_knowledge_base_import.py | 新建 |

### 10.2 参考文档

- 需求：`scripts/import_to_datasets/QA_case/QA的case梳理思路.md`
- 数据导入流程：`cursor_docs/020402-数据导入流程技术设计.md`
- unique_key 设计：`cursor_docs/020506-unique_key在导入流程中的生成与传递设计.md`
- 知识库模型：`backend/infrastructure/database/models/knowledge_base.py`
- DataSets 数据格式：`doc/总体设计规划/数据归档-schema/DataSets-数据格式设计.md`

---

## 11. 开发完成情况

| 阶段 | 序号 | 任务 | 状态 | 说明 |
|------|------|------|------|------|
| 第一阶段 | 1 | 实现 PgReader | ✅ 已完成 | readers/pg_reader.py，支持 fetch + iter_sheets |
| 第一阶段 | 2 | import_service 支持 sourceType=pg | ✅ 已完成 | 支持 excel/pg，PG 时先 fetch 再迭代 |
| 第二阶段 | 3 | CanonicalItem 扩展 response_rule、step1_metadata | ✅ 已完成 | canonical.py |
| 第二阶段 | 4 | 实现 KnowledgeBaseCleaner | ✅ 已完成 | cleaners/impl/knowledge_base.py |
| 第二阶段 | 5 | 注册 knowledge_base 清洗器 | ✅ 已完成 | registry.py |
| 第三阶段 | 7 | 单元测试 | ✅ 已完成 | test_pipeline_import.py、test_knowledge_base_import.py |
| 第三阶段 | 8 | 集成测试 | ⏸ 可选 | 端到端导入需真实 DB，未实现 |

**测试命令**：`pytest cursor_test/pipeline/test_pipeline_import.py cursor_test/pipeline/test_knowledge_base_import.py -v`

**配置示例**（import_config.import_config）：

```json
{
  "sourceType": "pg",
  "sourcePath": {"tableName": "gd2502_knowledge_base"},
  "cleaners": {"default": "knowledge_base"},
  "dataSetsId": "<目标 DataSet ID>",
  "clearBeforeImport": false
}
```
