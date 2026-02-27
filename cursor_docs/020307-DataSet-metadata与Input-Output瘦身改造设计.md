# DataSet metadata 与 Input/Output 瘦身改造设计

## 1. 背景与目标

### 1.1 现状问题

当前 Feishu 导入后的 DataSet Item 结构：

| 位置 | 字段 | 示例 |
|------|------|------|
| **input** | current_msg, history_messages, **context** | context 含 age、disease、血压、症状、用药等 |
| **expected_output** | response_message, flow_msgs, **other_meta_data** | other_meta_data 含 ext（如「疾病为：高血压且症状为：头昏头晕需预警」） |
| **metadata** | message_id, patient_id, doctor_id | 扁平结构 |

问题：
- context、ext 等「元信息」分散在 input/output 中，不利于标准化查询与筛选
- metadata 扁平，未按 DataSets-数据格式设计 的层级结构组织

### 1.2 改造目标

1. **other_meta_data（含 ext）** → 迁入 **metadata**
2. **input.context** → 迁入 **metadata**
3. **metadata** 按 `DataSets-数据格式设计.md` 的层级结构重组，并调整 key 命名

---

## 2. 目标 metadata 层级结构

参考 `doc/总体设计规划/数据归档-schema/DataSets-数据格式设计.md`，采用以下层级 key（英文、便于代码与 Langfuse 使用）：

| 一级 key | 说明 | 来源 |
|----------|------|------|
| `trace_query` | 标准化查询（trace） | trace / 数据清洗 |
| `data_cleaning_tags` | 标记信息（数据清洗） | 数据清洗 |
| `content_info` | 内容的信息（数据清洗） | 数据清洗 |
| `flow_info` | 流程的信息（trace） | trace |

### 2.1 各层级字段定义

**trace_query**（标准化查询）：
- `message_id`：消息 ID
- `session_id`：会话 ID（若有）
- `user_id`：用户 ID（若有）
- `flow_key`：流程 key（若有）
- `tags`：标签列表（若有）

**content_info**（内容的信息）：
- `user_info`：用户信息（原 input.context：age、disease、blood_pressure、symptom、medication、medication_status、habit、history_action）
- `doctor_info`：医生信息（doctor_id）
- `patient_info`：患者信息（patient_id）
- `ext`：扩展信息（原 other_meta_data.ext，如「疾病为：高血压且症状为：头昏头晕需预警」）

**data_cleaning_tags**（标记信息）：
- `ai_tags`：AI 标记
- `human_tags`：人工标记
- `dedup_tags`：去重标记

**flow_info**（流程的信息）：
- `flow_key`：流程 key
- `flow_name`：流程 name
- `flow_version`：流程版本

> 注：Feishu 导入场景暂无 trace_query.session_id、flow_info 等，可预留结构，后续由 trace 写入时填充。

---

## 3. 改造前后对比

### 3.1 Input

| 改造前 | 改造后 |
|--------|--------|
| current_msg | current_msg |
| history_messages | history_messages |
| **context**（age、disease 等） | **移除**，迁入 metadata.content_info.user_info |

### 3.2 Expected Output

| 改造前 | 改造后 |
|--------|--------|
| response_message | response_message |
| flow_msgs | flow_msgs |
| **other_meta_data**（ext） | **移除**，迁入 metadata.content_info.ext |

### 3.3 Metadata

| 改造前 | 改造后 |
|--------|--------|
| message_id | metadata.trace_query.message_id |
| patient_id | metadata.content_info.patient_info（或 patient_id 保持扁平兼容，见下） |
| doctor_id | metadata.content_info.doctor_info |
| （无） | metadata.content_info.user_info（原 context） |
| （无） | metadata.content_info.ext（原 other_meta_data.ext） |

---

## 4. 实现方案

### 4.1 方案 A：完全层级化

metadata 严格按层级组织：

```json
{
  "trace_query": {
    "message_id": "f98e3c10-2692-4660-8040-1e040a70d87d"
  },
  "content_info": {
    "user_info": {
      "age": 45,
      "disease": "高血压",
      "blood_pressure": "130/80",
      "symptom": "头晕",
      "medication": "降压药",
      "medication_status": "规律服药",
      "habit": "低盐饮食",
      "history_action": "action1"
    },
    "patient_info": "1993948901082382359",
    "doctor_info": "1922824398239559724",
    "ext": "疾病为：高血压且症状为：头昏头晕需预警，尽快回院"
  }
}
```

### 4.2 方案 B：层级 + 扁平兼容（推荐）

为兼容现有查询（如按 message_id、patient_id 筛选），在 metadata 根层保留常用扁平 key，同时提供层级结构：

```json
{
  "message_id": "f98e3c10-2692-4660-8040-1e040a70d87d",
  "patient_id": "1993948901082382359",
  "doctor_id": "1922824398239559724",
  "trace_query": {
    "message_id": "f98e3c10-2692-4660-8040-1e040a70d87d"
  },
  "content_info": {
    "user_info": { "age": 45, "disease": "高血压", ... },
    "patient_info": "1993948901082382359",
    "doctor_info": "1922824398239559724",
    "ext": "疾病为：高血压且症状为：头昏头晕需预警"
  }
}
```

---

## 5. 影响范围与改造任务

### 5.1 涉及文件

| 文件 | 改造内容 |
|------|----------|
| `parsers/canonical.py` | canonical_to_dataset_item：context → metadata.content_info.user_info；ext → metadata.content_info.ext；output 移除 other_meta_data；metadata 按新结构组装 |
| `parsers/cleaners/lsk.py` | 无逻辑变更，CanonicalItem 结构不变，仅转换层调整 |
| `parsers/cleaners/sh1128.py` | 同上 |
| `parsers/cleaners/sh1128_multi.py` | 同上 |
| `parsers/cleaners/sh1128_history_qa.py` | 同上 |
| `doc/.../DataSet-input-schema.json` | 移除或标记 context 为 deprecated |
| `doc/.../DataSet-output-schema.json` | 移除或标记 other_meta_data 为 deprecated |
| `doc/.../DataSet-metadata-schema.json` | 新增 metadata 层级 Schema |
| `cursor_test/test_feishu_import_*.py` | 断言 input 无 context、output 无 other_meta_data；metadata 含 content_info |

### 5.2 CanonicalItem 与 canonical_to_dataset_item

**CanonicalItem**：保持不变（仍有 context、ext），由转换层决定如何写入 DataSetItemData。

**canonical_to_dataset_item** 改造要点：
1. `input_data` 不再包含 `context`
2. `expected_output` 不再包含 `other_meta_data`
3. `item_metadata` 按新结构组装：
   - `trace_query.message_id`（及根层 `message_id` 若采用方案 B）
   - `content_info.user_info` = context
   - `content_info.patient_info` = patient_id
   - `content_info.doctor_info` = doctor_id
   - `content_info.ext` = ext

### 5.3 下游影响

- **评估 / 评分**：若依赖 input.context 或 output.other_meta_data，需改为从 metadata 读取
- **Chat 流程**：若从 DataSet 回放时使用 context，需改为从 metadata.content_info.user_info 读取

---

## 6. 实现任务清单

| 序号 | 任务 | 文件 |
|------|------|------|
| 1 | canonical_to_dataset_item：input 移除 context，output 移除 other_meta_data | parsers/canonical.py |
| 2 | canonical_to_dataset_item：metadata 按 trace_query、content_info 层级组装 | parsers/canonical.py |
| 3 | 新增 DataSet-metadata-schema.json（可选） | doc/.../数据归档-schema/ |
| 4 | 更新 DataSet-input-schema.json、DataSet-output-schema.json | doc/.../数据归档-schema/ |
| 5 | 更新单元测试 | cursor_test/ |
| 6 | 确认评估/Chat 等下游无破坏 | 人工检查 |

---

## 7. 与 DataSets-数据格式设计 的对应关系

| DataSets-数据格式设计 原文 | 本设计对应 |
|----------------------------|------------|
| 标准化查询（trace） | trace_query |
| 标记信息（数据清洗） | data_cleaning_tags |
| 内容的信息（数据清洗） | content_info（user_info、doctor_info、patient_info、ext） |
| 流程的信息（trace） | flow_info |
| input 当前会话、历史回话 | current_msg、history_messages（保持不变） |
| input 当前会话上下文对象 | 迁入 metadata.content_info.user_info |
| output 返回给用户的消息 | response_message（保持不变） |
| output 过程消息 | flow_msgs（保持不变） |

---

## 8. 完成情况

| 序号 | 任务 | 状态 | 说明 |
|------|------|------|------|
| 1 | canonical_to_dataset_item：input 移除 context，output 移除 other_meta_data | ✅ 已完成 | parsers/canonical.py |
| 2 | canonical_to_dataset_item：metadata 按 trace_query、content_info 层级组装 | ✅ 已完成 | 方案 A 完全层级化 |
| 3 | 新增 DataSet-metadata-schema.json | ✅ 已完成 | doc/.../数据归档-schema/ |
| 4 | 更新 DataSet-input-schema.json、DataSet-output-schema.json | ✅ 已完成 | 移除 context、other_meta_data |
| 5 | 更新单元测试 | ✅ 已完成 | cursor_test/test_feishu_canonical_metadata.py，5 个用例 |

**测试命令**：`pytest cursor_test/test_feishu_canonical_metadata.py -v`
