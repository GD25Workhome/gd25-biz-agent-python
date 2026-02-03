# DataSet metadata 结构二次改造设计

## 1. 背景

基于 020307 已完成的 metadata 层级化改造，实际使用中发现以下问题，需进行二次调整：

1. **trace_query 二级结构**：`trace_query.message_id` 等嵌套不利于扁平查询，希望改为根层 key 加前缀
2. **patient_info、doctor_info 为字符串**：当前 `patient_info: "1993948901082382359"` 无法扩展，需改为对象结构以支持后续增加其它属性

---

## 2. 改造点

### 2.1 标准化查询：取消 trace_query 二级，改用 query_ 前缀

**改造前**（020307 方案 A）：
```json
{
  "trace_query": {
    "message_id": "f98e3c10-2692-4660-8040-1e040a70d87d",
    "session_id": "xxx",
    "user_id": "xxx",
    "flow_key": "xxx",
    "tags": []
  }
}
```

**改造后**：
```json
{
  "query_message_id": "f98e3c10-2692-4660-8040-1e040a70d87d",
  "query_session_id": "xxx",
  "query_user_id": "xxx",
  "query_flow_key": "xxx",
  "query_tags": []
}
```

| 原 key | 新 key |
|--------|--------|
| trace_query.message_id | query_message_id |
| trace_query.session_id | query_session_id |
| trace_query.user_id | query_user_id |
| trace_query.flow_key | query_flow_key |
| trace_query.tags | query_tags |

> 注：Feishu 导入当前仅填充 query_message_id，其余由 trace 等后续填充。

### 2.2 patient_info、doctor_info：改为对象结构

**改造前**：
```json
{
  "content_info": {
    "patient_info": "1993948901082382359",
    "doctor_info": "1922824398239559724"
  }
}
```

**改造后**：
```json
{
  "content_info": {
    "patient_info": {
      "patient_id": "1993948901082382359"
    },
    "doctor_info": {
      "doctor_id": "1922824398239559724"
    }
  }
}
```

便于后续扩展，例如：
```json
{
  "patient_info": {
    "patient_id": "1993948901082382359",
    "patient_name": "张三",
    "age": 45
  },
  "doctor_info": {
    "doctor_id": "1922824398239559724",
    "doctor_name": "李医生"
  }
}
```

---

## 3. 完整 metadata 示例（改造后）

```json
{
  "query_message_id": "f98e3c10-2692-4660-8040-1e040a70d87d",
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
    "patient_info": {
      "patient_id": "1993948901082382359"
    },
    "doctor_info": {
      "doctor_id": "1922824398239559724"
    },
    "ext": "疾病为：高血压且症状为：头昏头晕需预警，尽快回院"
  }
}
```

---

## 4. 影响范围

| 文件 | 改造内容 |
|------|----------|
| parsers/canonical.py | trace_query → query_message_id 等；patient_info/doctor_info 改为对象 |
| doc/.../DataSet-metadata-schema.json | 更新 trace_query、patient_info、doctor_info 定义 |
| cursor_test/test_feishu_canonical_metadata.py | 更新断言 |

---

## 5. 实现任务清单

| 序号 | 任务 | 文件 |
|------|------|------|
| 1 | canonical_to_dataset_item：trace_query 改为 query_message_id 等扁平 key | parsers/canonical.py |
| 2 | canonical_to_dataset_item：patient_info、doctor_info 改为 { patient_id }、{ doctor_id } 对象 | parsers/canonical.py |
| 3 | 更新 DataSet-metadata-schema.json | doc/.../数据归档-schema/ |
| 4 | 更新单元测试 | cursor_test/test_feishu_canonical_metadata.py |

---

## 6. 完成情况

| 序号 | 任务 | 状态 |
|------|------|------|
| 1 | canonical_to_dataset_item：trace_query 改为 query_message_id | ✅ 已完成 |
| 2 | canonical_to_dataset_item：patient_info、doctor_info 改为对象格式 | ✅ 已完成 |
| 3 | 更新 DataSet-metadata-schema.json | ✅ 已完成 |
| 4 | 更新单元测试 | ✅ 已完成 |

**测试命令**：`pytest cursor_test/test_feishu_canonical_metadata.py -v`
