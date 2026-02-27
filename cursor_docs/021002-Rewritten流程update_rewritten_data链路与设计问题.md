# Rewritten 流程：update_rewritten_data 链路与设计问题

## 一、链路概览

```
Worker 拉取 DataItemsRewrittenRecord(init)
    → run_one_rewritten(rec)   [持有 rec.id]
    → 用 rec.source_dataset_id + rec.source_item_id 查 DataSetsItemsRecord → item_record
    → _run_one(item_record, dataset_id, graph)
        → build_state_from_record(record=item_record, dataset_id, ...)  【SET source_*】
        → graph.ainvoke(initial_state)
            → ... flow 执行 ...
            → update_rewritten_data_node
                → _extract_source_ids(state)  【USE source_*】
                → get_by_source_ids(source_dataset_id, source_item_id)  【USE → 查库】
                → repo.update(existing.id, **kwargs)  【USE existing.id 更新】
```

---

## 二、source_dataset_id / source_item_id 的 Set 位置

| 位置 | 文件:行 | 说明 |
|------|---------|------|
| **唯一 Set 点** | `backend/pipeline/rewritten_service.py` 第 157-165 行 | `build_state_from_record()` 内构造 `prompt_vars`：`source_dataset_id=dataset_id`，`source_item_id=record.id`。其中 `record` 为 `DataSetsItemsRecord`（即上面的 `item_record`），`dataset_id` 为入参。 |

代码引用：

```157:166:backend/pipeline/rewritten_service.py
    prompt_vars: Dict[str, Any] = {
        "q_context": q_context,
        ...
        "source_dataset_id": dataset_id,
        "source_item_id": record.id,
    }
```

即：**整条链路上，这两个字段只在这一个地方被写入 state**，且来源于「原始条目」的 dataset_id 与 item id，而不是「当前改写任务」的主键。

---

## 三、source_dataset_id / source_item_id 的 Use 位置

| 位置 | 文件:行 | 说明 |
|------|---------|------|
| 读取 | `backend/domain/flows/implementations/update_rewritten_data_func.py` 第 77-87 行 | `_extract_source_ids(state)`：从 `state["persistence_edges_var"]` 与 `state["prompt_vars"]` 合并结果中取 `source_dataset_id`、`source_item_id`。 |
| 查询 | 同文件 第 186-216 行 | `execute()` 中：若二者缺失则打日志并跳过；否则调用 `repo.get_by_source_ids(source_dataset_id, source_item_id)` 查询「要更新的记录」。 |
| 更新 | 同文件 第 231 行 | 查到 `existing` 后执行 `repo.update(existing.id, **kwargs)`，即用「按 source 查到的单条」的主键做更新。 |

设计文档/注释中的「根据 source_dataset_id + source_item_id 查找已有记录」即指上述「用这两个字段查库再更新」的逻辑（见 `update_rewritten_data_func.py` 第 6、163 行注释）。

---

## 四、设计问题分析

### 4.1 当前设计的隐含假设

- 表中对同一组 `(source_dataset_id, source_item_id)` **至多一条** 待更新记录（init/processing）。
- 因此可以用「来源维度」唯一定位到一条 `DataItemsRewritten`，再用其 `id` 做 `update`。

### 4.2 与真实数据/业务的不一致

- 表中**允许**同一组 `(source_dataset_id, source_item_id)` 存在**多条**记录（例如历史多次创建、不同 batch、重跑等）。
- `get_by_source_ids` 使用 `scalar_one_or_none()`，在返回多行时必然抛出 `MultipleResultsFound`。
- 即：**用「来源」定位「要更新的那条改写记录」在存在多行时不可行**，这是当前报错的直接原因。

### 4.3 上游为何不应依赖 source_* 做「查库再更新」

- Worker 端在 `run_one_rewritten(rec)` 里**已经明确知道**当前任务对应的是哪一条改写记录：**`rec`（DataItemsRewrittenRecord）及其 `rec.id`**。
- 整条链路中，**`rec.id` 从未被传入 state**；传入的只是从「原始条目」推导出的 `source_dataset_id` 和 `source_item_id`。
- 因此：
  - **定位维度错了**：应用「当前任务对应的 DataItemsRewritten 主键」来更新，而不是用「来源」在库里再查一次。
  - **上游不应依赖**「只给 source_dataset_id + source_item_id，让 update_rewritten_data_func 自己去查再更新」这种设计，因为一旦同一来源有多条改写记录，就会多行报错且语义歧义（不知道该更新哪一条）。

---

## 五、建议的正确设计

| 项目 | 当前（有问题） | 建议 |
|------|----------------|------|
| 传入 state 的标识 | 仅 `source_dataset_id`、`source_item_id`（来自 DataSetsItemsRecord） | 增加 **`rewritten_record_id`**（即当前任务对应的 `DataItemsRewritten.id`），由 Worker 侧在构建 state 时写入。 |
| update_rewritten_data_func 的更新逻辑 | 用 source_dataset_id + source_item_id 调 `get_by_source_ids` 得到 `existing`，再 `repo.update(existing.id, ...)` | 用 **rewritten_record_id** 直接 `repo.update(rewritten_record_id, ...)`（或先按 id get 再 update），**不再**用 source_* 查库定位记录。 |
| 可选 | — | 若仍希望校验「当前记录确实属于该 source」，可在 update 前按 id 查一条，校验 `source_dataset_id`/`source_item_id` 与 state 一致；但**定位**应仅依赖 `rewritten_record_id`。 |

这样：

- 一条 flow 只更新「本任务」对应的那条 `DataItemsRewritten`，无歧义。
- 不再出现「同一 source 多行」导致的 `MultipleResultsFound`。
- 上游「Set」的是「当前改写任务 id」，下游「Use」的也是「该 id」做更新，链路一致且可追溯。

---

## 六、小结

- **Set**：`source_dataset_id` / `source_item_id` 仅在 **rewritten_service.build_state_from_record** 的 `prompt_vars` 中设置，值来自 DataSetsItemsRecord 的 dataset_id 与 record.id。
- **Use**：在 **update_rewritten_data_func** 的 `_extract_source_ids` 与 `execute` 中被读取，并用于 `get_by_source_ids` 查库和 `repo.update(existing.id, ...)`。
- **设计问题**：用 (source_dataset_id, source_item_id) 定位要更新的记录，在存在多条时不可行且语义不清；应改为由上游传入 **rewritten_record_id**，下游按 id 直接更新。

---

## 七、修改方案（按「只传 id、下游只按 id 取值」实现）

以下为具体代码修改逻辑，便于实现前检查。

### 7.1 约定

- 上游不再向 state 写入 `source_dataset_id`、`source_item_id`，改为写入 **`rewritten_record_id`**（当前任务对应的 `DataItemsRewritten.id`）。
- 下游 **仅** 从 state 取 `rewritten_record_id`，用 **id** 查库；取到则继续更新，取不到则 **抛出异常**（不再「打日志并跳过」）。

### 7.2 `backend/pipeline/rewritten_service.py`

| 修改点 | 说明 |
|--------|------|
| **build_state_from_record** | 增加入参 `rewritten_record_id: Optional[str] = None`。在 `prompt_vars` 中：**删除** `source_dataset_id`、`source_item_id`；**新增** `"rewritten_record_id": rewritten_record_id`（仅当 `rewritten_record_id` 非空时写入，或始终写入由下游判断空值）。docstring 中「prompt_vars: source_dataset_id, source_item_id」改为「prompt_vars: rewritten_record_id（供 update_rewritten_data_func 按 id 更新）」。 |
| **_run_one** | 增加入参 `rewritten_record_id: Optional[str] = None`。调用 `build_state_from_record(..., rewritten_record_id=rewritten_record_id)` 时传入该参数。 |
| **run_one_rewritten** | 调用 `_run_one` 时传入当前改写任务主键：`_run_one(item_record, dataset_id, graph, rewritten_record_id=rec.id)`。 |

说明：`_run_batch_parallel` 若将来被使用，需在调用 `_run_one` 时传入对应的 `rewritten_record_id`（例如先创建 init 记录再传每条 `rec.id`），否则 flow 执行到 update 节点会因缺少 id 而抛异常。

### 7.3 `backend/domain/flows/implementations/update_rewritten_data_func.py`

| 修改点 | 说明 |
|--------|------|
| **新增 _extract_rewritten_record_id** | 从 state 的 `persistence_edges_var` 与 `prompt_vars` 合并结果中读取 `rewritten_record_id`，做空串/None 规范化后返回 `Optional[str]`（与现有 _extract_source_ids 来源一致，仅 key 改为 `rewritten_record_id`）。 |
| **execute 主流程** | 1）用 `_extract_rewritten_record_id(state)` 取得 `rewritten_record_id`。2）若为空（None 或空串）：**抛出异常**（例如 `ValueError("update_rewritten_data_node: rewritten_record_id 缺失")`），不再「打日志并返回 result_summary」。3）用 `repo.get_by_id(rewritten_record_id)` 查记录；若为 None：**抛出异常**（例如 `ValueError("update_rewritten_data_node: 未找到记录 id=...")`）。4）若查到：执行 `repo.update(rewritten_record_id, **kwargs)`（不再使用 `existing.id`，直接使用入参 id）、`session.commit()`，并将结果摘要写入 state 后返回。 |
| **不再使用的逻辑** | 删除对 `_extract_source_ids` 的调用及基于 `source_dataset_id`/`source_item_id` 的「缺失则打日志并返回」分支；删除 `get_by_source_ids` 的调用及「未找到记录则打日志并写 result_summary」分支。可保留 `_extract_source_ids` 函数定义以便兼容或后续删除。 |
| **文档/注释** | 文件头与 execute 的 docstring 中「根据 source_dataset_id + source_item_id 查找」改为「根据 state 中的 rewritten_record_id（改写任务主键）查记录并更新；id 缺失或记录不存在时抛出异常」。 |

### 7.4 仓储层

- **DataItemsRewrittenRepository** 继承 BaseRepository，已有 `get_by_id(id)`，无需新增方法；**无需**在本次修改中调整 `get_by_source_ids`（可保留供其他场景使用）。

### 7.5 行为对比小结

| 项目 | 修改前 | 修改后 |
|------|--------|--------|
| state 中用于定位的键 | source_dataset_id, source_item_id | rewritten_record_id |
| 查库方式 | get_by_source_ids(source_dataset_id, source_item_id) | get_by_id(rewritten_record_id) |
| id 缺失时 | 打日志，写 result_summary 并 return | 抛出异常 |
| 按 id 查不到记录时 | 打日志，写 result_summary 并 return | 抛出异常 |
| 更新调用 | repo.update(existing.id, **kwargs) | repo.update(rewritten_record_id, **kwargs) |

按上述修改后，整条链路仅依赖「当前任务对应的改写记录 id」，避免同一 source 多行导致的 MultipleResultsFound，且取不到或查不到时通过异常终止任务，便于上层（如 Worker）统一捕获并标记失败。

---

## 八、修改完成情况

| 任务 | 状态 | 说明 |
|------|------|------|
| 7.2 rewritten_service.py：build_state_from_record 改传 rewritten_record_id | 已完成 | 增加入参 `rewritten_record_id: Optional[str] = None`；prompt_vars 中删除 source_dataset_id/source_item_id，新增 rewritten_record_id；docstring 已更新。 |
| 7.2 rewritten_service.py：_run_one / run_one_rewritten | 已完成 | _run_one 增加入参 rewritten_record_id，并传入 build_state_from_record；run_one_rewritten 调用 _run_one(..., rewritten_record_id=rec.id)。 |
| 7.3 update_rewritten_data_func.py：按 id 取值并抛异常 | 已完成 | 新增 _extract_rewritten_record_id；execute 仅用 rewritten_record_id，缺失或 get_by_id 查不到时抛出 ValueError；使用 repo.get_by_id + repo.update(rewritten_record_id, **kwargs)；删除对 _extract_source_ids、get_by_source_ids 的调用；文档/注释已更新。原 _extract_source_ids 已移除（insert_rewritten_data_func 自有实现）。 |
| 7.4 仓储层 | 无需改动 | 使用 BaseRepository 已有 get_by_id。 |

**完成时间**：按文档第七章方案完成代码修改，未新增测试用例（为流程集成逻辑，建议通过改写 Worker 端到端验证）。
