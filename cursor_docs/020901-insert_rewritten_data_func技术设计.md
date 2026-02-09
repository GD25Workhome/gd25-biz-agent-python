# insert_rewritten_data_func 技术设计文档

## 1. 概述

### 1.1 文档目的

本文档描述 `insert_rewritten_data_func` 的技术设计，该 Function 节点用于将 `rewritten_agent_node` 的 JSON 输出解析、映射并持久化到 `pipeline_data_items_rewritten` 表。

### 1.2 背景与上下文

- **流程位置**：`config/flows/pipeline_step2/flow.yaml`
- **上游节点**：`rewritten_agent_node`（Agent 类型），输出严格 JSON 格式
- **下游**：流程结束（END）
- **数据表**：`pipeline_data_items_rewritten`（`DataItemsRewrittenRecord` 模型）

### 1.3 数据流概览

```
rewritten_agent_node 输出 JSON
        ↓
   state.edges_var（Agent 解析后自动写入）
        ↓
   insert_rewritten_data_node（本 Function）
        ↓
   解析 → 映射 → 写入 pipeline_data_items_rewritten
```

---

## 2. 表结构变更（新增字段）

### 2.1 新增字段清单

在 `pipeline_data_items_rewritten` 表中新增以下字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `rewrite_basis` | Text | 改写依据，直接映射 Agent 输出的「改写依据」 |
| `scenario_confidence` | Numeric(10,4) | 场景置信度，直接映射 Agent 输出的「场景置信度」（0–1） |
| `trace_id` | String(100) | 流程执行时的 traceId，用于链路追踪 |
| `status` | String(20) | 执行状态：`success` / `failed` |
| `execution_metadata` | JSONB | 执行过程元数据，存储失败原因及可扩展的流程执行信息 |

### 2.2 execution_metadata 结构约定

- **成功时**：可为 `null` 或 `{}`
- **失败时**：至少包含 `failure_reason`，可扩展如：
  ```json
  {
    "failure_reason": "edges_var 中无有效改写结果",
    "stage": "extract_edges_var",
    "agent_output_snippet": "..."
  }
  ```
- **可扩展字段**：诸如 `stage`、`agent_output_snippet`、`parse_error`、`validation_results` 等流程执行过程信息，按需追加

---

## 3. 输入约定

### 3.1 state 中的来源

`insert_rewritten_data_func` 从 `FlowState` 中读取以下数据：

| 来源 | 用途 |
|------|------|
| `state.edges_var` | rewritten_agent_node 输出的 JSON 解析结果（Agent 框架自动提取） |
| `state.prompt_vars` 或 `state.persistence_edges_var` | 来源 ID：`source_dataset_id`、`source_item_id` |
| `state.trace_id` | 流程执行时的 traceId，写入 `trace_id` 字段 |

### 3.2 rewritten_agent 输出格式（prompts/rewritten_agent.md）

Agent 输出为**严格 JSON**，无额外文本：

```json
{
  "场景描述": "string",
  "患者提问": "string",
  "回复案例": "string",
  "回复规则": "string",
  "场景": "string",
  "子场景": "string",
  "改写依据": "string",
  "场景置信度": "0-1之间的任意小数，比如：0.8",
  "标签": {
    "场景标签": ["tag1", "tag2", ...],
    "患者标签": ["tag1", "tag2", ...],
    "患者发言标签": ["tag1", "tag2", ...],
    "回答标签": ["tag1", "tag2", ...],
    "补充标签": ["tag1", "tag2", ...]
  }
}
```

**说明**：提示词约定「任意属性未提取到则省略」，因此各字段均可为 `undefined` 或空。实际执行时可能出现拿不到数据的情况，需通过状态字段标记。

### 3.3 Agent 框架对 edges_var 的写入行为

依据 `agent_creator.py` 逻辑：

- Agent 输出为字符串时，会尝试提取 `{ ... }` 中的 JSON
- 将 JSON 对象的**每个 key** 直接写入 `state.edges_var`
- 排除字段：`response_content`、`reasoning_summary`、`additional_fields`

因此，`insert_rewritten_data_func` 可从 `edges_var` 中直接读取：

- `edges_var["场景描述"]`
- `edges_var["患者提问"]`
- `edges_var["回复案例"]`
- `edges_var["回复规则"]`
- `edges_var["场景"]`
- `edges_var["子场景"]`
- `edges_var["改写依据"]`
- `edges_var["场景置信度"]`
- `edges_var["标签"]`

---

## 4. 字段映射

### 4.1 完整映射表

| Agent 输出 / state 来源 | DataItemsRewrittenRecord 字段 | 类型 | 说明 |
|------------------------|-------------------------------|------|------|
| 场景描述 | scenario_description | Text | nullable |
| 患者提问 | rewritten_question | Text | nullable |
| 回复案例 | rewritten_answer | Text | nullable |
| 回复规则 | rewritten_rule | Text | nullable |
| 场景 | scenario_type | String(1000) | nullable |
| 子场景 | sub_scenario_type | String(1000) | nullable |
| **改写依据** | **rewrite_basis** | **Text** | **新增字段，直接映射** |
| **场景置信度** | **scenario_confidence** | **Numeric(10,4)** | **新增字段，直接映射** |
| 标签 | ai_tags | JSONB | 原样存储 |
| — | source_dataset_id | String(100) | 来自 prompt_vars / persistence_edges_var |
| — | source_item_id | String(100) | 同上 |
| — | **trace_id** | **String(100)** | **新增，来自 state.trace_id** |
| — | **status** | **String(20)** | **新增，success / failed** |
| — | **execution_metadata** | **JSONB** | **新增，失败原因及可扩展执行信息** |

### 4.2 特殊处理

1. **场景置信度 → scenario_confidence**
   - 输入可能是字符串（如 `"0.8"`）或数字
   - 需做类型转换与校验：0–1 范围，无效则 `None`

2. **改写依据 → rewrite_basis**
   - 直接映射，无需再存入 ai_score_metadata

3. **标签 → ai_tags**
   - 标签为嵌套对象，直接 JSON 序列化后存入 JSONB

4. **source_dataset_id / source_item_id**
   - 由调用方在 invoke 时通过 `prompt_vars` 或 `persistence_edges_var` 传入
   - 若缺失，可记录为 `None`（状态为 failed 时写入 execution_metadata 说明）

5. **trace_id**
   - 从 `state.trace_id` 读取，用于链路追踪

6. **status 与 execution_metadata**
   - 成功：`status = "success"`，`execution_metadata = null` 或 `{}`
   - 失败：`status = "failed"`，`execution_metadata` 至少包含 `failure_reason`，可扩展其它执行过程信息

---

## 5. 实现设计

### 5.1 类与职责

| 组件 | 职责 |
|------|------|
| `InsertRewrittenDataNode` | 继承 `BaseFunctionNode`，实现 `execute(state)` |
| `get_key()` | 返回 `"insert_rewritten_data_func"`，与 flow.yaml 中 `function_key` 一致 |
| 解析/映射逻辑 | 抽取 edges_var、规范化类型、映射到 ORM 字段 |
| `DataItemsRewrittenRepository` | 扩展 create 参数，支持新增字段；需随表结构变更 |

### 5.2 执行流程

```
1. 从 state 提取 trace_id、source_dataset_id、source_item_id
2. 从 state.edges_var 提取改写结果
3. 若 edges_var 无有效数据：
   - 仍写入一条记录，status = "failed"，execution_metadata = {"failure_reason": "..."}
   - 其它业务字段为 null
4. 若有有效数据：
   - 类型规范化（场景置信度、标签等）
   - 构建完整字段映射（含 rewrite_basis、scenario_confidence、trace_id、status、execution_metadata）
   - status = "success"，execution_metadata = null
5. 获取 AsyncSession，调用 DataItemsRewrittenRepository.create
6. commit 事务
7. 可选：将入库结果摘要写入 state.edges_var（如 inserted_count、record_id）
8. 返回更新后的 state
```

### 5.3 异常与边界（含「拿不到数据」场景）

| 场景 | 处理策略 |
|------|----------|
| edges_var 无有效改写结果 | **不抛异常**：写入一条 status="failed" 记录，execution_metadata 记录 failure_reason，其它业务字段为 null |
| 场景置信度非法（非 0–1 数值） | 记为 `None`，不阻流程，status 仍为 success |
| source_dataset_id / source_item_id 缺失 | 记为 `None`，写入 execution_metadata 说明「来源 ID 缺失」；若业务要求必填，可设 status="failed" |
| JSON 解析失败（标签格式异常） | ai_tags 存 `None`，不阻流程；可选择性写入 execution_metadata 记录 parse_error |
| trace_id 缺失 | trace_id 存 `None`，建议 execution_metadata 中记录「trace_id 缺失」便于排查 |

### 5.4 文件规划

| 文件 | 操作 |
|------|------|
| `backend/infrastructure/database/models/data_items_rewritten.py` | 新增字段：rewrite_basis、scenario_confidence、trace_id、status、execution_metadata |
| `alembic/versions/xxx_add_rewritten_status_fields.py` | 新增迁移脚本 |
| `backend/domain/flows/implementations/insert_rewritten_data_func.py` | 新建 |
| `backend/domain/flows/implementations/__init__.py` | 增加导入与注册 |
| `function_registry` | 注册 `insert_rewritten_data_func` |
| `backend/infrastructure/database/repository/data_items_rewritten_repository.py` | 若 create 使用 **kwargs，仅需兼容新字段；否则扩展 create 签名 |

---

## 6. 与 rewrite_service 的衔接

### 6.1 state 构建约定

`rewritten_service` 在 invoke 流程前需构建 state，至少包含：

- `prompt_vars` 或 `persistence_edges_var`：
  - `source_dataset_id`：来源 DataSet ID
  - `source_item_id`：来源 DataItem ID
- `trace_id`：流程执行时的 traceId（通常在 FlowState 顶层）
- `prompt_vars` 中用于提示词占位符的变量（已有）：
  - `q_context`、`current_message`、`history_messages`
  - `manual_ext`、`response_message`、`response_rule`

### 6.2 调用链示意

```
rewritten_service.invoke_single_item(dataset_id, item_id, item_data)
  → 构建 state（含 prompt_vars / persistence_edges_var / trace_id）
  → FlowManager.invoke(graph, state)
  → rewritten_agent_node 执行
  → insert_rewritten_data_node 执行（本 Function）
  → 写入 pipeline_data_items_rewritten（含 status、execution_metadata）
```

---

## 7. 潜在风险与对策

| 风险 | 对策 |
|------|------|
| Agent 输出夹杂非 JSON 文本 | agent_creator 已做 `{` `}` 提取，一般可解析；若仍失败，写 status="failed" + execution_metadata |
| 标签结构不符合预期 | 用 `isinstance` 校验，异常时存 `None` 或空对象 |
| 并发写入同一条 source_item_id | 当前设计为单条插入；若需幂等，可考虑 `get_by_source_item_id` 后 upsert |
| 中文 key 与 ORM 英文字段对应易错 | 建议集中维护映射字典，便于维护与单测 |
| 失败记录业务字段全 null | 通过 status、execution_metadata 区分，便于后续筛选与重试 |

---

## 8. 测试建议

| 测试类型 | 内容 |
|----------|------|
| 单元测试 | 解析逻辑：edges_var 齐全 / 部分缺失 / 异常类型 |
| 单元测试 | 映射逻辑：场景置信度、改写依据、标签的规范化 |
| 单元测试 | 失败场景：无数据时写入 status="failed"、execution_metadata 正确 |
| 集成测试 | 依赖真实 DB，验证写入后可正确查询，含 status 筛选 |
| 边界测试 | 空字符串、空数组、非法数值、缺失 source_id、缺失 trace_id |

---

## 9. 附录

### 9.1 参考实现

- `InsertRagDataNode`（`insert_rag_data_func.py`）：从 edges_var 读取 cases、解析、入库
- `agent_creator.py`：Agent 输出写入 edges_var 的机制

### 9.2 相关文档

- `doc/总体设计规划/数据归档-schema/Step2-数据初步筛选.md`
- `config/flows/pipeline_step2/prompts/rewritten_agent.md`

### 9.3 表结构变更汇总

| 变更类型 | 字段 | 说明 |
|----------|------|------|
| 新增 | rewrite_basis | Text，改写依据 |
| 新增 | scenario_confidence | Numeric(10,4)，场景置信度 |
| 新增 | trace_id | String(100)，流程 traceId |
| 新增 | status | String(20)，success / failed |
| 新增 | execution_metadata | JSONB，失败原因及可扩展执行信息 |
