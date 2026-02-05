# DataSets 数据清理能力技术设计文档

**文档编号**：020504  
**创建日期**：2025-02-05  
**需求来源**：用户需求  
**关联文档**：cursor_docs/020402-数据导入流程技术设计.md  

---

## 1. 概述

### 1.1 目标

在现有 `import_service.py` 导入流程及数据项管理界面基础上，增加 DataSets 的数据清理能力，满足以下需求：

1. **导入配置项**：在导入管理的配置 JSON 中增加「是否清除旧数据」配置项，导入前可选清空目标 DataSet 下所有数据项
2. **数据项管理界面**：在数据项管理 Tab 中，在「新建数据项」按钮旁增加「清理所有数据」按钮，支持手动清空当前 DataSet 下所有数据项

### 1.2 设计原则

- 与现有 `020402` 导入流程设计保持一致
- 复用 `DataSetsItemsRepository`，不引入新表
- 清理操作需二次确认，避免误删

---

## 2. 需求拆解

### 2.1 需求一：导入配置增加「是否清除旧数据」

| 项目 | 说明 |
|------|------|
| 配置字段 | `clearBeforeImport`（布尔值，默认 `false`） |
| 存储位置 | `import_config` 表的 `import_config` JSON 字段 |
| 生效时机 | 执行导入时，若为 `true`，在读取数据并写入前，先删除目标 `dataSetsId` 下所有 items |
| 影响范围 | 仅影响 `execute_import` 主流程 |

### 2.2 需求二：数据项管理界面增加「清理所有数据」按钮

| 项目 | 说明 |
|------|------|
| 界面位置 | `pipeline_dataset_items.js`，与「新建数据项」按钮同一行 |
| 交互流程 | 点击 → 弹窗确认「确定清空该数据集下所有数据项？此操作不可恢复。」→ 调用 API → 刷新列表 |
| 权限 | 与删除单条数据项一致，无额外限制 |

---

## 3. 配置结构变更

### 3.1 import_config.import_config 字段扩展

在 `020402` 文档定义的 JSON 结构基础上，新增可选字段：

```json
{
  "sourceType": "excel",
  "sourcePath": { "filePath": "static/rag_source/uat_data/xxx.xlsx" },
  "sheetNames": null,
  "cleaners": {
    "default": "lsk",
    "常见问题及单轮": "sh1128_multi"
  },
  "dataSetsId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "clearBeforeImport": true
}
```

### 3.2 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| clearBeforeImport | boolean | 否 | false | 导入前是否清除目标 DataSet 下所有数据项。为 true 时，在写入新数据前先删除该 dataSetsId 下全部 items |

### 3.3 兼容性

- 未配置或为 `null` 时，视为 `false`，保持原有行为（追加写入）
- 配置为 `true` 时，导入前执行清空逻辑

---

## 4. 后端改造

### 4.1 DataSetsItemsRepository 扩展

**文件**：`backend/infrastructure/database/repository/data_sets_items_repository.py`

**新增方法**：

```python
async def delete_all_by_dataset_id(self, dataset_id: str) -> int:
    """
    删除指定 dataset 下所有数据项。

    Args:
        dataset_id: 数据集 ID

    Returns:
        删除的记录数
    """
    from sqlalchemy import delete
    stmt = delete(DataSetsItemsRecord).where(
        DataSetsItemsRecord.dataset_id == dataset_id
    )
    result = await self.session.execute(stmt)
    return result.rowcount
```

### 4.2 import_service.py 流程改造

**文件**：`backend/pipeline/import_service.py`

**改造点**：在「6. 迭代 sheet → 清洗 → 入库」之前，增加清空逻辑：

```python
# 5.5 可选：导入前清空
clear_before = meta.get("clearBeforeImport") is True
if clear_before:
    items_repo = DataSetsItemsRepository(session)
    deleted_count = await items_repo.delete_all_by_dataset_id(dataset.id)
    logger.info("导入前清空 DataSet %s，删除 %d 条", data_sets_id, deleted_count)

# 6. 迭代 sheet → 清洗 → 入库
for sheet_name, df in reader.iter_sheets():
    ...
```

**依赖**：需在 `import_service.py` 中增加 `DataSetsItemsRepository` 的导入。

### 4.3 新增 API：批量清空 DataSet 数据项

**文件**：`backend/app/api/routes/data_cleaning.py`

**接口定义**：

| 方法 | 路径 | 说明 |
|------|------|------|
| DELETE | `/api/v1/data-cleaning/datasets/{dataset_id}/items` | 清空指定 DataSet 下所有数据项 |

**路径参数**：`dataset_id` — 数据集 ID

**响应**（成功 200）：

```json
{
  "message": "清空成功",
  "deleted_count": 42
}
```

**响应**（失败 4xx/5xx）：

```json
{
  "detail": "数据集合不存在"
}
```

**实现逻辑**：

1. 校验 `dataset_id` 对应的 DataSet 是否存在
2. 调用 `DataSetsItemsRepository.delete_all_by_dataset_id(dataset_id)`
3. 返回删除条数

**注意**：与单条删除 `DELETE /datasets/{dataset_id}/items/{item_id}` 区分，此处无 `item_id`，表示批量清空。

---

## 5. 前端改造

### 5.1 数据项管理界面（pipeline_dataset_items.js）

**改造点**：在顶部操作栏，「新建数据项」按钮旁增加「清理所有数据」按钮。

**布局示意**：

```
┌─────────────────────────────────────────────────────────────────┐
│ {{ datasetName }} — 共 {{ itemsTotal }} 条    [新建数据项] [清理所有数据] │
└─────────────────────────────────────────────────────────────────┘
```

**实现要点**：

1. 新增 `clearAllItems` 方法：
   - 调用 `ElMessageBox.confirm` 二次确认
   - 确认文案：「确定清空该数据集下所有数据项？此操作不可恢复。」
   - 调用 `DELETE ${API_PREFIX}/datasets/${props.datasetId}/items`
   - 成功提示「已清空 X 条数据」
   - 调用 `loadItems()` 刷新列表

2. 模板中增加按钮：

```html
<el-button size="small" type="danger" plain @click="clearAllItems" :icon="Delete">清理所有数据</el-button>
```

3. 当 `itemsTotal === 0` 时，可禁用「清理所有数据」按钮（可选，提升体验）

### 5.2 导入管理配置 JSON 编辑

**文件**：`frontend/js/pipeline_import_manage.js`（或配置编辑弹窗所在文件）

**改造点**：在导入配置的 JSON 编辑界面中，需支持用户编辑 `clearBeforeImport` 字段。

- 若当前使用 JSONEditor 或 JSON 文本编辑 `import_config`，用户可直接在 JSON 中增加 `"clearBeforeImport": true`
- 若需单独表单项，可在编辑表单中增加「导入前清除旧数据」开关，与 JSON 合并后提交

**建议**：首版可依赖用户在 JSON 中手动添加，后续若需要更友好交互，再增加独立表单项。

---

## 6. 流程时序

### 6.1 导入流程（含 clearBeforeImport）

```
用户点击「执行导入」
    → 后端 execute_import(config_id)
    → 查询 import_config，解析 meta
    → 校验 dataSetsId、sourceType、cleaners
    → 若 meta.clearBeforeImport === true
        → DataSetsItemsRepository.delete_all_by_dataset_id(dataSetsId)
    → 迭代 sheet → 清洗 → 入库
    → 返回 stats
```

### 6.2 数据项管理界面「清理所有数据」

```
用户点击「清理所有数据」
    → ElMessageBox.confirm 确认
    → DELETE /api/v1/data-cleaning/datasets/{dataset_id}/items
    → 后端校验 dataset 存在 → delete_all_by_dataset_id
    → 返回 deleted_count
    → 前端 loadItems() 刷新列表
```

---

## 7. 开发任务清单

### 7.1 后端

| 序号 | 任务 | 产出 |
|------|------|------|
| 1 | DataSetsItemsRepository 增加 delete_all_by_dataset_id | data_sets_items_repository.py |
| 2 | import_service 增加 clearBeforeImport 逻辑 | import_service.py |
| 3 | 新增 DELETE /datasets/{id}/items 批量清空 API | data_cleaning.py |

### 7.2 前端

| 序号 | 任务 | 产出 |
|------|------|------|
| 4 | 数据项管理界面增加「清理所有数据」按钮及逻辑 | pipeline_dataset_items.js |
| 5 | （可选）导入配置编辑支持 clearBeforeImport 表单项 | pipeline_import_manage.js |

### 7.3 测试

| 序号 | 任务 | 产出 |
|------|------|------|
| 6 | 单元测试：clearBeforeImport 导入前清空 | test_pipeline_import.py |
| 7 | 单元测试：delete_all_by_dataset_id | test_data_sets_items_repository.py 或新建 |

---

## 8. 风险与注意事项

| 项目 | 说明 |
|------|------|
| 数据安全 | 清理操作不可恢复，需前端二次确认、后端无额外保护 |
| 并发 | 若导入与手动清理同时进行，可能出现竞态；建议用户避免并行操作 |
| API 路径 | `DELETE /datasets/{id}/items` 与 `DELETE /datasets/{id}/items/{item_id}` 路径不同，路由可正确区分 |

---

## 9. 附录

### 9.1 参考文档

- 数据导入流程：`cursor_docs/020402-数据导入流程技术设计.md`
- 数据导入管理：`cursor_docs/020401-数据导入管理模块技术设计.md`

### 9.2 涉及文件清单

| 文件 | 变更类型 |
|------|----------|
| backend/infrastructure/database/repository/data_sets_items_repository.py | 新增方法 |
| backend/pipeline/import_service.py | 修改流程 |
| backend/app/api/routes/data_cleaning.py | 新增端点 |
| frontend/js/pipeline_dataset_items.js | 新增按钮与逻辑 |

---

## 10. 开发完成情况

| 阶段 | 任务 | 状态 | 说明 |
|------|------|------|------|
| 后端 | DataSetsItemsRepository 增加 delete_all_by_dataset_id | ✅ 已完成 | data_sets_items_repository.py |
| 后端 | import_service 增加 clearBeforeImport 逻辑 | ✅ 已完成 | import_service.py |
| 后端 | 新增 DELETE /datasets/{id}/items 批量清空 API | ✅ 已完成 | data_cleaning.py |
| 前端 | 数据项管理界面增加「清理所有数据」按钮及逻辑 | ✅ 已完成 | pipeline_dataset_items.js |
| 前端 | 导入配置 clearBeforeImport 表单项 | ⏭ 未实现 | 首版依赖 JSON 手动添加 |
| 测试 | clearBeforeImport 导入前清空 | ✅ 已完成 | test_data_clearing.py |
| 测试 | delete_all_by_dataset_id | ✅ 已完成 | test_data_clearing.py |

**测试命令**：`pytest cursor_test/pipeline/test_data_clearing.py -v`

**访问入口**：`http://localhost:8000/static/data-cleaning.html`（需先启动后端服务）
