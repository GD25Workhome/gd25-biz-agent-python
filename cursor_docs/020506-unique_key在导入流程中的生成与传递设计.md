# unique_key 在导入流程中的生成与传递技术设计文档

**文档编号**：020506  
**创建日期**：2025-02-05  
**需求来源**：数据项管理、去重与追溯  
**关联文档**：cursor_docs/020402-数据导入流程技术设计.md、cursor_docs/020504-DataSets数据清理能力技术设计.md  

---

## 1. 概述

### 1.1 背景与目标

当前导入流程中，`DatasetItemWriter.write_item()` 已支持 `unique_key` 参数，但 `import_service.py` 未传入该值，导致入库时 `unique_key` 恒为 `null`。为支持数据去重、增量导入与业务追溯，需在导入流程中正确生成并传递 `unique_key`。

**核心难点**：不同清洗器（LSK、Sh1128、Sh1128Multi、Sh1128HistoryQA 等）的 `unique_key` 生成逻辑各异，需为每个流程定制，同时不破坏现有架构。

**设计目标**：
1. 在 `backend/pipeline/cleaners/impl` 中实现各流程的 `unique_key` 定制逻辑
2. 建立从清洗器到入库执行器的传递链路
3. 保持对现有代码的兼容，不破坏三阶段流程架构

### 1.2 当前流程梳理

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  ExcelReader    │ ──► │  BaseSheetCleaner│ ──► │ DatasetItemWriter│
│  iter_sheets()  │     │  clean(row, df)  │     │  write_item()   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                        │                        │
         │                        │  List[CanonicalItem]   │
         │                        │  canonical_to_dataset_item
         │                        │                        │
         │                        │                        │ unique_key 当前恒为 None
```

**数据流现状**：
- `cleaner.clean(row, df)` → `List[CanonicalItem]`
- `canonical_to_dataset_item(item)` → `DatasetItemDto`（仅含 input、output、metadata）
- `writer.write_item(dataset_id, item=dto, source=..., status=1)`，**未传 unique_key**

---

## 2. 各清洗器 unique_key 生成逻辑差异分析

### 2.1 清洗器与数据源对比

| 清洗器 | 数据源 | 1 行 → N 条 | 可用唯一标识字段 | unique_key 规则 |
|--------|--------|-------------|------------------|-----------------|
| LskCleaner | 4.1 lsk_副本.xlsx | 1→1 | ids(message_id, patient_id, doctor_id) | **message_id** |
| Sh1128Cleaner | sh-1128_副本.xlsx | 1→1 | message_id, patient_id | **message_id** |
| Sh1128MultiCleaner | 常见问题及单轮 Sheet | 1→N | 每轮有 message_id | message_id |
| Sh1128HistoryQACleaner | 患者无数据+历史会话 | 1→1 | 同 Sh1128Cleaner | **message_id**（继承父类） |

### 2.2 业务规则差异

- **LSK**：`ids` 列为复合格式，通过 `extract_lsk_ids` 解析得到 message_id、patient_id、doctor_id；unique_key 使用 message_id
- **Sh1128**：`message_id`、`patient_id` 分列，通过 `extract_message_id` 解析 message_id；unique_key 使用 message_id
- **Sh1128Multi**：1 行拆成多轮 Q/A，每轮可能对应一个 message_id，需用 message_id:idx 区分
- **Sh1128HistoryQA**：继承 Sh1128Cleaner，沿用父类 message_id 逻辑

**结论**：无法在 `import_service` 或 `canonical_to_dataset_item` 中统一生成 `unique_key`，必须由各清洗器在 `impl` 层按业务规则定制。

---

## 3. 方案选型

### 3.1 方案对比

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A. CanonicalItem 扩展 | 在 CanonicalItem 增加 `unique_key` 字段 | 实现简单，清洗器完全自洽，传递链清晰 | 需改 CanonicalItem、import_service |
| B. 清洗器 get_unique_key() | 基类增加 `get_unique_key(item, row, df, idx)` | 生成逻辑与 clean 分离 | 需回传 row/df/idx，接口臃肿；clean 与 get_unique_key 可能重复解析 |
| C. 返回元组 | clean() 返回 `List[Tuple[CanonicalItem, str]]` | 显式携带 unique_key | 破坏现有返回类型，影响面大 |
| D. metadata 携带 | 将 unique_key 放入 metadata，writer 从中读取 | 不改 CanonicalItem | 污染业务 metadata，语义不清；需 writer 或 canonical 层解析 |

### 3.2 选定方案：CanonicalItem 扩展（方案 A）

**已选定**：采用方案 A，由各清洗器在构造 CanonicalItem 时设置 `unique_key`，基于当前已实现的 lsk.py、sh1128.py 进行逻辑转换。

**选择理由**：
1. 生成逻辑放在清洗器内部，与业务强相关的字段由业务方负责，符合单一职责
2. 传递链短：`CanonicalItem.unique_key` → `import_service` → `writer.write_item(unique_key=...)`
3. 不改变 `clean()` 返回类型，仅扩展 CanonicalItem 字段
4. `canonical_to_dataset_item` 不处理 unique_key（其职责是 input/output/metadata），保持职责清晰
5. 向后兼容：未设置的清洗器 `unique_key` 为 None，写入时依旧为 null，行为与现状一致

---

## 4. 详细设计

### 4.1 CanonicalItem 扩展

**文件**：`backend/pipeline/cleaners/canonical.py`

```python
@dataclass
class CanonicalItem:
    current_msg: str = ""
    history_messages: List[Dict[str, str]] = field(default_factory=list)
    response_message: str = ""
    message_id: Optional[str] = None
    patient_id: Optional[str] = None
    doctor_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    ext: Optional[str] = None
    unique_key: Optional[str] = None  # 新增：业务唯一 key，由各清洗器按规则生成
```

**说明**：
- `unique_key` 为可选，默认 `None`
- `canonical_to_dataset_item()` **不**处理 `unique_key`，不写入 metadata
- unique_key 仅用于传递给 `DatasetItemWriter.write_item()`

### 4.2 清洗器 impl 改造（切入位置）

各清洗器在构造 `CanonicalItem` 时设置 `unique_key`，统一使用 **message_id** 作为 unique_key。以下基于当前已实现的 lsk.py、sh1128.py 进行逻辑转换。

#### 4.2.1 LskCleaner（lsk.py）

**现有代码**：已通过 `extract_lsk_ids` 解析得到 `ids_data`，其中含 `message_id`。

**改造**：在构造 CanonicalItem 时增加 `unique_key=ids_data["message_id"]`。

```python
# 当前 clean() 中已有：
ids_data = (
    extract_lsk_ids(row.get(self._MSG_ID_COL))
    if self._MSG_ID_COL in df.columns
    else {"message_id": None, "patient_id": None, "doctor_id": None}
)

# 改造：在 return 的 CanonicalItem 中增加 unique_key
return [
    CanonicalItem(
        current_msg=current,
        history_messages=history_messages,
        response_message=response,
        message_id=ids_data["message_id"],
        patient_id=ids_data["patient_id"],
        doctor_id=ids_data["doctor_id"],
        context=context,
        ext=ext,
        unique_key=ids_data["message_id"],  # 新增：message_id 作为 unique_key
    )
]
```

#### 4.2.2 Sh1128Cleaner（sh1128.py）

**现有代码**：已通过 `extract_message_id` 解析得到 `msg_id`。

**改造**：在构造 CanonicalItem 时增加 `unique_key=msg_id`。

```python
# 当前 clean() 中已有：
msg_id = extract_message_id(row.get(self._MSG_ID_COL)) if self._MSG_ID_COL in df.columns else None

# 改造：在 return 的 CanonicalItem 中增加 unique_key
return [
    CanonicalItem(
        current_msg=current,
        history_messages=history_messages,
        response_message=response,
        message_id=msg_id,
        patient_id=patient_id,
        context=context,
        ext=ext,
        unique_key=msg_id,  # 新增：message_id 作为 unique_key
    )
]
```

#### 4.2.3 Sh1128MultiCleaner（sh1128_multi.py）

1 行 → 多 CanonicalItem，每轮使用对应的 `message_id` 作为 unique_key：

```python
# 在循环内构造 CanonicalItem 时增加 unique_key
for i in range(n):
    msg_id = msg_ids[i] if i < len(msg_ids) else None
    result.append(CanonicalItem(..., unique_key=msg_id))
```

若 `msg_id` 为空，可依赖 4.4 节的 import_service 兜底逻辑。

#### 4.2.4 Sh1128HistoryQACleaner（sh1128_history_qa.py）

继承 Sh1128Cleaner，重写 `_parse_history_messages()` 而未重写 `clean()`，故沿用父类 `clean()`。父类改造后已设置 `unique_key=msg_id`，**无需额外改动**。

### 4.3 import_service 传递链改造

**文件**：`backend/pipeline/import_service.py`

**当前逻辑**（约 169-177 行）：

```python
canonical_items = cleaner.clean(row, df)
for item in canonical_items:
    dto = canonical_to_dataset_item(item)
    await writer.write_item(
        dataset_id=dataset.id,
        item=dto,
        source=source_value,
        status=1,
    )
```

**改造后**：

```python
canonical_items = cleaner.clean(row, df)
for item in canonical_items:
    dto = canonical_to_dataset_item(item)
    await writer.write_item(
        dataset_id=dataset.id,
        item=dto,
        source=source_value,
        unique_key=item.unique_key,  # 新增：从 CanonicalItem 传递
        status=1,
    )
```

**影响范围**：仅增加一行传参，不改变流程结构。

### 4.4 多 Item 场景下的 row 级兜底（可选）

对于 Sh1128MultiCleaner 等 1 行 → N 条场景，若清洗器无法在 `clean()` 内生成唯一 key（例如无 message_id），可考虑在 `import_service` 层做兜底：

```python
for sub_idx, item in enumerate(canonical_items):
    dto = canonical_to_dataset_item(item)
    uk = item.unique_key
    if not uk and len(canonical_items) > 1:
        # 兜底：source 已含 sheet，可拼接 row_idx 与 sub_idx
        uk = f"{source_value}:{idx}:{sub_idx}"  # idx 为 df.iterrows() 的行号
    await writer.write_item(..., unique_key=uk, ...)
```

**注意**：`source_value` 形式为 `excel:{file_path}:{sheet_name}`，已包含 sheet 信息。`idx` 为 DataFrame 行索引，在 `for idx, row in df.iterrows()` 中可得。

是否采用此兜底策略可根据业务决定；若清洗器能自洽生成唯一 key，则可不实现。

---

## 5. 传递链路与架构合规性检查

### 5.1 传递链路

```
cleaner.clean(row, df)
    → List[CanonicalItem]  每个 item 可含 unique_key
        ↓
canonical_to_dataset_item(item)
    → DatasetItemDto       （不处理 unique_key）
        ↓
writer.write_item(..., unique_key=item.unique_key)
    → repo.create(..., unique_key=unique_key)
        → 写入 pipeline_data_sets_items.unique_key
```

### 5.2 架构影响评估

| 组件 | 变更类型 | 说明 |
|------|----------|------|
| CanonicalItem | 扩展字段 | 新增 `unique_key: Optional[str] = None`，默认 None 保持兼容 |
| canonical_to_dataset_item | 无变更 | 不处理 unique_key，职责不变 |
| BaseSheetCleaner | 无变更 | 接口不变，不强制实现 unique_key |
| 各 impl 清洗器 | 按需改造 | 在构造 CanonicalItem 时设置 unique_key，不设则保持 None |
| import_service | 小改动 | 调用 write_item 时增加 `unique_key=item.unique_key` |
| DatasetItemWriter | 无变更 | 已支持 unique_key 参数 |
| DataSetsItemsRepository | 无变更 | create 已支持 unique_key |

### 5.3 向后兼容性

- 未设置 `unique_key` 的清洗器：`item.unique_key` 为 None，写入时 `unique_key` 为 null，与当前行为一致
- 新增清洗器：可按需实现 unique_key，不实现也不影响运行
- 现有单元测试：仅需对涉及 CanonicalItem 构造的测试补充 `unique_key` 字段（若断言了结构），否则可不改

---

## 6. 实现任务清单

### 6.1 必做

| 序号 | 任务 | 文件 | 说明 |
|------|------|------|------|
| 1 | CanonicalItem 增加 unique_key 字段 | canonical.py | `unique_key: Optional[str] = None` |
| 2 | import_service 传递 unique_key | import_service.py | `write_item(..., unique_key=item.unique_key)` |
| 3 | LskCleaner 设置 unique_key | impl/lsk.py | `unique_key=ids_data["message_id"]` |
| 4 | Sh1128Cleaner 设置 unique_key | impl/sh1128.py | `unique_key=msg_id` |
| 5 | Sh1128MultiCleaner 设置 unique_key | impl/sh1128_multi.py | `unique_key=msg_id` |
| 6 | Sh1128HistoryQACleaner | impl/sh1128_history_qa.py | 无需改，继承父类已设置的 unique_key |

### 6.2 可选

| 序号 | 任务 | 说明 |
|------|------|------|
| 7 | import_service 兜底逻辑 | 多 Item 且 item.unique_key 为空时，用 source:row:sub_idx 兜底 |
| 8 | 单元测试 | 覆盖 unique_key 从清洗器到写入的传递，及未设置时的兼容 |

### 6.3 不建议的做法

- 在 `canonical_to_dataset_item` 中生成 unique_key（无法访问 row/df，且违反职责单一）
- 在 `DatasetItemWriter` 中从 metadata 解析 unique_key（污染业务 metadata）
- 修改 `clean()` 返回类型为元组（破坏现有架构）

---

## 7. 风险与注意事项

| 项目 | 说明 |
|------|------|
| unique_key 唯一性 | 需保证同一 dataset 内 unique_key 不重复，否则影响 get_by_unique_key、去重逻辑 |
| 空值处理 | message_id 为空时 unique_key 为 None，写入时数据库为 null；可选 4.4 节兜底策略 |
| 历史数据 | 已有数据的 unique_key 为 null，与新增逻辑共存无问题；若需回填需单独脚本 |
| 配置化 | 若未来希望通过配置指定 unique_key 生成规则，可在清洗器内读取配置，本设计不排除后续扩展 |

---

## 8. 附录

### 8.1 涉及文件清单

| 文件 | 变更类型 |
|------|----------|
| backend/pipeline/cleaners/canonical.py | 扩展 CanonicalItem |
| backend/pipeline/import_service.py | 传递 unique_key |
| backend/pipeline/cleaners/impl/lsk.py | 设置 unique_key |
| backend/pipeline/cleaners/impl/sh1128.py | 设置 unique_key |
| backend/pipeline/cleaners/impl/sh1128_multi.py | 设置 unique_key |
| backend/pipeline/cleaners/impl/sh1128_history_qa.py | 视父类情况按需调整 |

### 8.2 参考文档

- 数据导入流程：`cursor_docs/020402-数据导入流程技术设计.md`
- DataSets 数据清理：`cursor_docs/020504-DataSets数据清理能力技术设计.md`
- 数据导入管理：`cursor_docs/020401-数据导入管理模块技术设计.md`

---

## 10. 开发完成情况

| 序号 | 任务 | 状态 | 说明 |
|------|------|------|------|
| 1 | CanonicalItem 增加 unique_key 字段 | ✅ 已完成 | canonical.py |
| 2 | import_service 传递 unique_key | ✅ 已完成 | import_service.py |
| 3 | LskCleaner 设置 unique_key | ✅ 已完成 | impl/lsk.py |
| 4 | Sh1128Cleaner 设置 unique_key | ✅ 已完成 | impl/sh1128.py |
| 5 | Sh1128MultiCleaner 设置 unique_key | ✅ 已完成 | impl/sh1128_multi.py |
| 6 | Sh1128HistoryQACleaner | ✅ 无需改 | 继承父类已设置的 unique_key |
| 8 | 单元测试 | ✅ 已完成 | test_pipeline_import.py 新增/补充 unique_key 断言 |

**测试命令**：`pytest cursor_test/pipeline/test_pipeline_import.py -v`

**测试覆盖**：17 个用例全部通过，含 `test_canonical_to_dataset_item_ignores_unique_key`、`test_execute_import_passes_unique_key_to_writer` 及 LSK/Sh1128/Sh1128Multi 清洗器 unique_key 断言。
