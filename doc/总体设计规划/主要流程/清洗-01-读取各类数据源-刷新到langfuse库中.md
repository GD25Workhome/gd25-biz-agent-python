# 数据清洗流程文档

本文档描述 Feishu Excel 导入 Langfuse Datasets 脚本（`import_feishu_excel.py`）的关键流程和核心设计。

---

## 1. 概述

### 1.1 脚本职责

将 `static/rag_source/uat_data/` 目录下的 Excel 测试数据清洗、规范化为统一格式，并导入 Langfuse Datasets，供 RAG 评估使用。

### 1.2 核心能力

- **多源适配**：支持不同 Excel、不同 Sheet 的差异化解析策略
- **统一输出**：所有清洗结果统一为 CanonicalItem 格式，再转换为 DataSet Input/Output Schema
- **可配置**：通过 Config 控制数据源、解析策略、重复导入行为等

---

## 2. 整体流程

### 2.1 总体设计流程（概括）

从总体设计视角，数据清洗流程可归纳为三个阶段：

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          数据清洗总体设计流程                                        │
└──────────────────────────────────────────────────────────────────────────────────┘

  各类数据源（Excel / CSV / API / ...）
           │
           ▼
  ┌────────────────────────────────────────────────────────────────────┐
  │ 阶段一：原始数据读取                                                  │
  │ · 按数据源类型选择读取器（当前以 Excel 为主）                          │
  │ · 支持不同格式数据源的扩展，保障数据能被程序识别与解析                  │
  │ · 输出：结构化的原始数据（如 DataFrame、行迭代器等）                    │
  └────────────────────────────────┬───────────────────────────────────┘
                                   │
                                   ▼
  ┌────────────────────────────────────────────────────────────────────┐
  │ 阶段二：数据初步清洗                                                  │
  │ · 按数据源格式选择清洗策略，统一输出规范格式                           │
  │ · 剔除无效数据（空行、必填项缺失等）                                   │
  │ · 字段格式转换、内容解析（如 content= 前缀去除、多轮 Q/A 拆分等）      │
  │ · 输出：统一的 DataSet 格式（input、expected_output、metadata）       │
  └────────────────────────────────┬───────────────────────────────────┘
                                   │
                                   ▼
  ┌────────────────────────────────────────────────────────────────────┐
  │ 阶段三：清洗后的数据入库                                              │
  │ · 新建或更新 DataSet（命名、Schema 绑定）                             │
  │ · 更新 DataSet 的 metadata（存储导入信息：来源、版本、导入时间等）     │
  │ · 可选清空旧 Items，实现覆盖导入                                      │
  │ · Items 入库：逐条写入 Langfuse DataSet                               │
  └────────────────────────────────────────────────────────────────────┘
```

**阶段说明**：

| 阶段 | 核心职责 | 设计要点 |
|------|----------|----------|
| **原始数据读取** | 从多种数据源获取原始数据 | 抽象读取接口，支持 Excel、CSV、API 等扩展；输出统一的结构化表示 |
| **数据初步清洗** | 规范化为 input/output/metadata 格式 | 策略模式按数据源选择清洗器；空值剔除、字段映射、格式转换 |
| **清洗后入库** | 持久化到 Langfuse DataSet | DataSet 创建/更新、metadata 记录导入信息、Items 批量写入 |

### 2.2 实际代码流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          数据清洗主流程                                        │
└─────────────────────────────────────────────────────────────────────────────┘

  Excel 文件列表 (Config.excel_files)
           │
           ▼
  ┌────────────────────┐
  │ 遍历每个 Excel      │
  │ - 文件存在校验      │
  │ - sheet_include     │
  │   _mapping 过滤     │
  └────────┬───────────┘
           │
           ▼
  ┌────────────────────┐     ┌──────────────────────┐
  │ ExcelReader        │────▶│ 迭代每个 Sheet        │
  │ iter_sheets()      │     │ (sheet_name, df)     │
  └────────────────────┘     └──────────┬───────────┘
                                        │
                                        ▼
  ┌──────────────────────────────────────────────────────────────┐
  │ 1. 策略选择：Config.get_parser_type(excel_name, sheet_name)   │
  │    → get_cleaner_by_type(cleaner_type)                        │
  ├──────────────────────────────────────────────────────────────┤
  │ 2. 创建 DataSet：DatasetCreator.create_or_update_dataset()    │
  │    - 按 feishu/excelName/sheetName 命名                       │
  │    - 设置 input_schema、expected_output_schema                │
  ├──────────────────────────────────────────────────────────────┤
  │ 3. 可选清空：Config.clear_before_import → clear_dataset_items │
  ├──────────────────────────────────────────────────────────────┤
  │ 4. 行级处理：for row in df.iterrows()                         │
  │    ┌─────────────────────────────────────────────────────┐   │
  │    │ cleaner.is_empty_row(row) → 跳过                     │   │
  │    │ cleaner.clean(row, df) → List[CanonicalItem]         │   │
  │    │ for item in canonical_items:                         │   │
  │    │   canonical_to_dataset_item(item) → DataSetItemData  │   │
  │    │   writer.write_item(dataset_name, dataset_item)      │   │
  │    └─────────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌────────────────────┐
  │ 汇总统计输出        │
  │ success/fail/skip  │
  └────────────────────┘
```

---

## 3. 关键流程详解

### 3.1 入口与初始化

```python
# main() 入口
langfuse = Langfuse()
creator = DatasetCreator(langfuse)   # DataSet 创建与 Schema 设置
writer = DatasetItemWriter(langfuse) # Item 写入
```

- **Config 驱动**：所有参数在 `config.py` 中配置，无需命令行传参
- **单次运行**：一次执行处理 `excel_files` 中列出的所有 Excel

### 3.2 Excel 与 Sheet 过滤

| 步骤 | 逻辑 | 配置项 |
|------|------|--------|
| Excel 过滤 | 文件存在性检查；`sheet_include_mapping` 非空时，仅处理映射中的 Excel | `sheet_include_mapping` |
| Sheet 过滤 | 空 Sheet 跳过；`sheet_include_mapping` 非空时，仅处理映射中的 Sheet | `sheet_include_mapping` |

- `sheet_include_mapping = {}`：处理所有 Excel 的所有 Sheet
- `sheet_include_mapping = {"4.1 lsk_副本": ["Sheet1"]}`：仅处理该 Excel 的 Sheet1

### 3.3 清洗器选择

```
优先级：sheet_parser_mapping > excel_parser_mapping > default_parser_type
```

| 配置层 | 示例 | 说明 |
|--------|------|------|
| Sheet 级 | `"sh-1128_副本/常见问题及单轮": "sh1128_multi"` | 同一 Excel 内不同 Sheet 使用不同策略 |
| Excel 级 | `"4.1 lsk_副本": "lsk"` | 该 Excel 默认使用 lsk 策略 |
| 默认 | `default_parser_type: "lsk"` | 未指定时的兜底策略 |

**清洗器类型与对应实现**：

| 类型 | 说明 | 行→Item 映射 |
|------|------|--------------|
| `lsk` | 4.1 lsk_副本.xlsx 格式 | 1 行 → 1 Item |
| `sh1128` | sh-1128_副本 通用格式 | 1 行 → 1 Item |
| `sh1128_multi` | 多轮 Q/A 拆分 | 1 行 → N Item |
| `sh1128_history_qa` | 历史会话 Q/A 解析 | 1 行 → 1 Item |

### 3.4 行级清洗主循环

```python
# 核心循环（简化）
for idx, row in df.iterrows():
    if cleaner.is_empty_row(row, df):
        sheet_stats["skipped"] += 1
        continue

    canonical_items = cleaner.clean(row, df)   # 清洗 → 规范格式
    for item in canonical_items:
        dataset_item = canonical_to_dataset_item(item)  # 转换
        writer.write_item(dataset_name, dataset_item)   # 写入
        sheet_stats["success"] += 1
```

**流程链路**：

1. **空行判断**：`is_empty_row()` 决定是否跳过
2. **清洗**：`clean()` 将 Excel 行解析为 `List[CanonicalItem]`
3. **格式转换**：`canonical_to_dataset_item()` 转为 DataSet Item 格式
4. **写入**：`write_item()` 调用 Langfuse API 创建 Item

---

## 4. 核心设计

### 4.1 清洗器策略模式

**基类**：`BaseSheetCleaner`（`parsers/cleaners/base.py`）

```python
class BaseSheetCleaner(ABC):
    @abstractmethod
    def clean(self, row: pd.Series, df: pd.DataFrame) -> List[CanonicalItem]:
        """清洗单行，返回 0 个或多个 CanonicalItem"""
        pass

    @abstractmethod
    def is_empty_row(self, row: pd.Series, df: pd.DataFrame) -> bool:
        """是否为空行（跳过）"""
        pass
```

- **职责**：Excel 行 → `List[CanonicalItem]`，屏蔽不同 Sheet 的列结构差异
- **注册**：`parsers/cleaners/__init__.py` 中的 `_CLEANER_REGISTRY`，通过 `get_cleaner_by_type()` 按类型获取实例
- **扩展**：新增清洗器只需实现基类并注册，主流程无需改动

### 4.2 CanonicalItem 规范格式

**定义**：`parsers/canonical.py`

```python
@dataclass
class CanonicalItem:
    current_msg: str = ""           # 当前会话消息
    history_messages: List[Dict[str, str]] = []  # 历史消息 [{"type":"human","content":...}, ...]
    response_message: str = ""      # 期望响应
    message_id: Optional[str] = None
    patient_id: Optional[str] = None
    doctor_id: Optional[str] = None
    context: Dict[str, Any] = {}    # 上下文（年龄、疾病、血压等）
    ext: Optional[str] = None
```

- **作用**：作为「清洗后」与「DataSet 写入前」的统一中间格式
- **与 Schema 对应**：Input/Output Schema 字段与 CanonicalItem 一一对应，转换层无需再解析
- **方案 A（层级化）**：`context`、`ext` 等迁入 `metadata.content_info`，input/output 仅保留核心字段

### 4.3 数据转换链路

```
Excel 行 (pd.Series)
       │
       ▼ cleaner.clean()
CanonicalItem (规范格式)
       │
       ▼ canonical_to_dataset_item()
DataSetItemData (input, expected_output, metadata)
       │
       ▼ writer.write_item()
Langfuse create_dataset_item()
```

**DataSetItemData 结构**（按方案 A）：

| 目标 | 来源 |
|------|------|
| `input.current_msg` | `CanonicalItem.current_msg` |
| `input.history_messages` | `CanonicalItem.history_messages` |
| `expected_output.response_message` | `CanonicalItem.response_message` |
| `metadata.content_info` | `context`、`patient_id`、`doctor_id`、`ext` |
| `metadata.query_message_id` | `CanonicalItem.message_id` |

### 4.4 DataSet 创建与重复导入

**创建**：`DatasetCreator.create_or_update_dataset()`

- 命名：`{prefix}/{excelName}/{sheetName}`，默认 prefix 为 `feishu`
- Schema：从 Config 指定路径加载 `DataSet-input-schema.json`、`DataSet-output-schema.json`
- Metadata：记录 `excel_name`、`sheet_name`、`parser_type`、`import_time` 等

**重复导入**：`Config.clear_before_import = True`（默认）

- 导入前调用 `clear_dataset_items()`，拉取并删除已有 Items
- 采用「拉取到空页为止」策略，避免 API 分页元数据不准确导致未清空干净
- 实现「覆盖」而非「追加」

---

## 5. 主要组件说明

| 组件 | 路径 | 职责 |
|------|------|------|
| 主入口 | `import_feishu_excel.py` | 编排整体流程，遍历 Excel/Sheet，调用清洗与写入 |
| 配置 | `config.py` | 数据源路径、解析策略映射、Schema 路径、重复导入开关 |
| Excel 读取 | `utils/excel_reader.py` | `iter_sheets()` 迭代 Sheet，返回 `(sheet_name, df)` |
| 清洗器 | `parsers/cleaners/` | 各策略实现 `clean()`、`is_empty_row()` |
| 规范格式 | `parsers/canonical.py` | `CanonicalItem` 定义与 `canonical_to_dataset_item()` |
| DataSet 创建 | `dataset/creator.py` | 创建/更新 DataSet、设置 Schema、清空 Items |
| Item 写入 | `dataset/item_writer.py` | `write_item()` 调用 Langfuse API |

---

## 6. 清洗策略示例（LSK）

以 `LskCleaner` 为例，说明单行清洗逻辑：

**列映射**：

- `新会话` → `current_msg`
- `新会话响应` → `response_message`（需 `strip_content_prefix` 去除 `content=` 前缀）
- `ids` → `message_id`、`patient_id`、`doctor_id`（正则提取）
- `历史会话`、`历史会话响应` → `history_messages`（按「第N轮提问/响应」解析后合并）
- `年龄`、`疾病`、`血压`、`症状`、`用药` 等 → `context`

**空行判断**：`新会话`、`新会话响应` 任一为空则跳过

**输出**：1 行 → 1 个 `CanonicalItem`

---

## 7. 运行方式

```bash
cd 项目根目录
python scripts/import_to_datasets/feishu_ceshi_case/import_feishu_excel.py
```

- 环境：需配置 `.env` 中的 Langfuse 相关变量
- 配置：所有参数在 `config.py` 中设置

---

## 8. 错误处理与统计

- **单行失败**：解析异常时记录日志，`sheet_stats["fail"] += 1`，继续处理后续行
- **汇总**：每个 Sheet 和全局输出 `success`、`fail`、`skipped` 统计
- **退出码**：若 `total_stats["fail"] > 0`，脚本以 `sys.exit(1)` 退出
