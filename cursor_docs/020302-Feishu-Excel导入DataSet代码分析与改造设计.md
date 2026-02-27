# Feishu Excel 导入 DataSet 代码分析与改造设计

> 本文档针对 `scripts/import_to_datasets/feishu_ceshi_case/` 的 DataSet 创建逻辑、Input/Output Schema 设置问题，以及 patient_id/message_id 存入 Item Metadata 的改造方案进行分析与设计。

---

## 一、代码结构分析

### 1.1 整体架构

```
import_feishu_excel.py (主入口)
    │
    ├── Config (配置)
    ├── ExcelReader (读取 Excel)
    │
    └── 按 Sheet 迭代
            │
            ├── get_parser_by_type() → 解析策略 (LskParser / Sh1128Parser)
            ├── FieldProcessorChain (责任链: Normalize → Assemble)
            │       │
            │       └── parser.to_dataset_item(row_data) → DataSetItemData
            │
            ├── DatasetCreator.create_or_update_dataset()  ← DataSet 创建 + Schema 设置
            ├── DatasetCreator.clear_dataset_items()      ← 可选：清空已有 Items
            └── DatasetItemWriter.write_item()             ← 写入单条 Item
```

### 1.2 核心模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| 主入口 | `import_feishu_excel.py` | 遍历 Excel、选择解析策略、调用 Creator/Writer |
| 配置 | `config.py` | 数据源路径、Schema 路径、解析策略映射、DataSet 命名 |
| 创建器 | `dataset/creator.py` | 创建 DataSet、设置 metadata、清空 Items |
| 写入器 | `dataset/item_writer.py` | 调用 `create_dataset_item` 写入 input/expected_output/metadata |
| 解析基类 | `parsers/base.py` | `extract_row_data`、`to_dataset_item`、字段转换工具 |
| 解析策略 | `parsers/strategies/*.py` | 列名映射（current_session、response、message_id） |
| 责任链 | `parsers/chain.py` | Normalize → Assemble，产出 `DataSetItemData` |

### 1.3 数据流

```
Excel 行 (pd.Series)
    → parser.extract_row_data(row, df)     → row_data (Dict)
    → FieldProcessorChain.process(row_data) → DataSetItemData
    → writer.write_item(dataset_name, item) → Langfuse create_dataset_item
```

### 1.4 DataSetItemData 结构

```python
@dataclass
class DataSetItemData:
    input: Dict[str, Any]           # 对应 Langfuse input
    expected_output: Dict[str, Any] # 对应 Langfuse expected_output
    metadata: Dict[str, Any]        # 对应 Langfuse dataset item metadata
```

---

## 二、Input/Output Schema 未设置成功的原因分析

### 2.1 现象

在 Langfuse UI 中创建 DataSet 后，**看不到 input_schema / expected_output_schema 的值**，Schema 校验功能无法生效。

### 2.2 根本原因（历史）

早期 Langfuse Python SDK 的 `create_dataset` 方法不支持 `input_schema` 和 `expected_output_schema` 参数，导致 Schema 无法通过 SDK 设置。

### 2.3 当前结论（2025-02-03 更新）

**Python SDK 的 `create_dataset` 已支持 `input_schema` 和 `expected_output_schema` 参数。** 直接传入即可：

```python
self._client.create_dataset(
    name=dataset_name,
    description="...",
    metadata=metadata,
    input_schema=input_schema,           # 完整 JSON Schema
    expected_output_schema=output_schema,
)
```

`creator.py` 已按此方式改造，Schema 可正确写入 Langfuse，UI 中 Schema Validation 区域会显示并生效。

**备选方案**：若 SDK 版本较旧不支持上述参数，可改用 REST API（`POST /api/public/v2/datasets`）直接调用，详见方案 A。

### 2.4 与官方文档的一致性

[Langfuse Datasets 文档](https://langfuse.com/docs/datasets) 的 Schema Enforcement 示例与当前 SDK 行为一致。

---

## 三、patient_id / message_id 存入 Item Metadata 的现状与改造

### 3.1 现状（改造后）

| 字段 | 提取位置 | 存储位置 | 是否在 Item Metadata |
|------|----------|----------|----------------------|
| `message_id` | `extract_row_data`（通过 `get_message_id_col()`） | `metadata` | ✅ 是 |
| `patient_id` | `extract_row_data`（通过 `get_patient_id_col()`） | `metadata` | ✅ 是 |

- `message_id`、`patient_id` 仅写入 `metadata`，不写入 `expected_output.other_meta_data`
- `other_meta_data` 仅保留 `ext` 等业务字段（若有）

### 3.2 Excel 列名与解析策略

| Excel 文件 | 解析策略 | message_id 列 | patient_id 列 |
|------------|----------|---------------|---------------|
| 4.1 lsk_副本.xlsx | LskParser | `ids` | 无 |
| sh-1128_副本.xlsx | Sh1128Parser | `message_id` | `patient_id` |

- 4.1 lsk_副本.xlsx 无 patient_id 列，LskParser 的 `get_patient_id_col()` 应返回 `None`
- sh-1128_副本.xlsx 有 patient_id 列，Sh1128Parser 的 `get_patient_id_col()` 应返回 `"patient_id"`

---

## 四、改造设计

### 4.1 Input/Output Schema 设置方案

#### 方案 A：Python SDK 直接传入（推荐，已采用）

**结论（2025-02-03）：Python SDK 的 `create_dataset` 支持 `input_schema` 和 `expected_output_schema` 参数。**

`creator.py` 已按此方式改造，直接传入即可：

```python
self._client.create_dataset(
    name=dataset_name,
    description="...",
    metadata=metadata,
    input_schema=input_schema,
    expected_output_schema=output_schema,
)
```

#### 方案 B：直接调用 REST API（备选，SDK 不支持时）

**调研结论：Langfuse 官方 REST API 支持 `inputSchema` / `expectedOutputSchema`。**

- **端点**：`POST /api/public/v2/datasets`
- **认证**：Basic Auth（username=Public Key, password=Secret Key）
- **测试脚本**：`cursor_test/datasets/test_langfuse_dataset_rest_api.py`

```python
resp = requests.post(
    f"{LANGFUSE_HOST}/api/public/v2/datasets",
    auth=(public_key, secret_key),
    headers={"Content-Type": "application/json"},
    json={
        "name": dataset_name,
        "description": "...",
        "inputSchema": input_schema_dict,
        "expectedOutputSchema": output_schema_dict,
    }
)
```

#### 方案 C：在 Langfuse UI 中手动配置

1. 打开 DataSet 详情页
2. 进入 Schema Validation 区域
3. 将 `doc/总体设计规划/数据归档-schema/` 下的 Schema 文件内容粘贴并保存

优点：无需改代码。  
缺点：每次新建 DataSet 需手动操作，不适合大批量自动化。

#### 方案 D：将完整 Schema 写入 metadata（折中）

将完整 Schema 写入 metadata 供参考。Langfuse 不会用 metadata 中的 schema 做校验，但可在 UI 中查看。

### 4.2 patient_id / message_id 存入 Item Metadata 的改造

**目标**：将 Excel 中的 `patient_id`、`message_id` 写入 Langfuse DataSet Item 的 `metadata`，便于在 Langfuse UI 中筛选、溯源。

**Excel 列名**：

| Excel | patient_id 列 | message_id 列 |
|-------|---------------|---------------|
| 4.1 lsk_副本.xlsx | 无 | `ids` |
| sh-1128_副本.xlsx | `patient_id` | `message_id` |

---

#### 4.2.1 BaseSheetParser 增加 patient_id 提取

**1. 新增 `get_patient_id_col` 方法**

在 `parsers/base.py` 的 `BaseSheetParser` 中增加（与 `get_message_id_col` 同级，非抽象，子类按需重写）：

```python
def get_patient_id_col(self) -> Optional[str]:
    """获取 patient_id 来源列名，无则返回 None。子类可重写。"""
    return None  # 默认无 patient_id
```

**2. 在 `extract_row_data` 中提取 patient_id**

在 `extract_row_data` 末尾、`return data` 前增加：

```python
patient_id_col = self.get_patient_id_col()
if patient_id_col and patient_id_col in df.columns:
    data["patient_id"] = convert_to_string(row.get(patient_id_col))
else:
    data["patient_id"] = None
```

**3. 各解析策略实现**

- **LskParser**：无需重写，使用基类默认 `return None`（4.1 lsk 无 patient_id 列）
- **Sh1128Parser**：重写 `get_patient_id_col()` 返回 `"patient_id"`

```python
# parsers/strategies/sh1128.py
def get_patient_id_col(self) -> Optional[str]:
    return "patient_id"
```

---

#### 4.2.2 to_dataset_item 写入 metadata

在 `parsers/base.py` 的 `to_dataset_item` 中，将 `return DataSetItemData(...)` 前的 `metadata={}` 改为：

```python
item_metadata: Dict[str, Any] = {}
if row_data.get("patient_id"):
    item_metadata["patient_id"] = row_data["patient_id"]
if row_data.get("message_id"):
    item_metadata["message_id"] = row_data["message_id"]

return DataSetItemData(
    input=input_data,
    expected_output=expected_output,
    metadata=item_metadata,
)
```

`message_id` 仅写入 metadata，不写入 `expected_output.other_meta_data`。

---

## 五、改造清单汇总

| 序号 | 改造项 | 涉及文件 | 说明 |
|------|--------|----------|------|
| 1 | Input/Output Schema | `dataset/creator.py` | 已采用方案 A（SDK 直接传入 input_schema/expected_output_schema） |
| 2 | patient_id 提取 | `parsers/base.py` | 新增 `get_patient_id_col()`，在 `extract_row_data` 中提取 |
| 3 | patient_id 列映射 | `parsers/strategies/sh1128.py` | 重写 `get_patient_id_col()` 返回 `"patient_id"`（LskParser 使用基类默认 None） |
| 4 | metadata 写入 | `parsers/base.py` | 在 `to_dataset_item` 中将 patient_id、message_id 写入 `DataSetItemData.metadata` |

---

## 六、附录：关键代码位置索引

| 功能 | 文件 | 行号/方法 |
|------|------|-----------|
| DataSet 创建 | `dataset/creator.py` | `create_or_update_dataset` |
| Schema 加载与 create_dataset 调用 | `dataset/creator.py` | 60-76 行 |
| Item 写入 | `dataset/item_writer.py` | `write_item` |
| 行数据提取 | `parsers/base.py` | `extract_row_data` |
| Item 组装 | `parsers/base.py` | `to_dataset_item` |
| message_id 提取 | `parsers/base.py` | `extract_message_id` |
| LSK 列映射 | `parsers/strategies/lsk.py` | `get_*_col` |
| SH1128 列映射 | `parsers/strategies/sh1128.py` | `get_*_col` |
