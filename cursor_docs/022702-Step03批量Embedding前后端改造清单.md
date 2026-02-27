## 1. 背景与目标

- **目标界面**：在 `data-cleaning.html` 中新增「Step03批量创建Embedding」页面。
- **数据来源**：复用现有「Step02数据清洗管理」列表（`/data-cleaning/data-items-rewritten`），基于 `pipeline_data_items_rewritten` 表。
- **核心能力**：
  - 基于来源 DataSets（`source_dataset_id`）、场景类型、子场景类型、执行状态等条件筛选 Step02 清洗结果；
  - 在当前筛选结果的基础上，一键创建「Embedding 批次任务」，由批次模块和 Embedding 模块异步执行。

---

## 2. 前端实现清单（不含具体代码）

### 2.1 主框架与路由改造

- **data-cleaning.html 增加菜单项**
  - 在左侧 `el-menu` 中新增一行：
    - 文案：`Step03批量创建Embedding`
    - 建议菜单 index：`embedding-batches`（或同类有语义的 key）。
  - 点击该菜单时，打开新的 Tab 页面，组件命名建议：`PipelineEmbeddingBatchComponent`。

- **Tab 管理逻辑扩展（`pipeline_cleaning.js`）**
  - 在 `tabConfigs` 中新增一项：
    - **key**：`embedding-batches`
    - **title**：`Step03批量创建Embedding`
    - **component**：`PipelineEmbeddingBatchComponent`
    - **icon**：可复用 `Document` 或单独选择图标。
  - `usePipelineCleaning` 的 `components` 注册中，增加 `PipelineEmbeddingBatchComponent`。

- **前端脚本引入**
  - 在 `data-cleaning.html` 底部 `script` 区域新增：
    - `js/pipeline_embedding_batches.js`
  - 在创建 Vue 应用时，将 `PipelineEmbeddingBatchComponent` 注册进 `components`。

### 2.2 Step03 列表页面结构

- **页面标题与头部区域**
  - 标题：`Step03 批量创建 Embedding`。
  - 右上角按钮：
    - 按钮名称：`批量Embedding`
    - 风格建议：`type="warning"` 或 `type="primary"`，尺寸 `size="small"`。
    - 行为与 Step01 原始数据项管理页面的「进行数据清洗」按钮一致：
      - 校验是否已选择【数据集】（来源 DataSetsId）；
      - 按当前查询条件封装请求参数；
      - 调用后端批次创建接口；
      - 使用通知组件展示批次创建结果（包含 `batch_code` 和任务条数），提示「将异步执行，可在批次管理或 Embedding 执行监控中查看进度」。

- **查询条件区域**
  - 总体要求：
    - 数据源：依然基于 `/data-cleaning/data-items-rewritten`。
    - 查询按钮、重置按钮行为与 Step02 数据清洗管理保持一致。
    - 查询字段顺序：**数据集 → 场景类型 → 子场景类型 → 执行状态 → 其它字段（抄 Step02）**。
  - **数据集（来源 DataSetsId，精确查询）**
    - 绑定字段：`source_dataset_id`。
    - 控件形式：**复用 Step01 原始数据项管理中的「数据集」选择控件**：
      - 支持弹出「选择数据集」对话框（`el-dialog + el-table`）；
      - 可通过 Tag 形式展示已选数据集；
      - 前端确定策略：
        - 建议限制为「单选或首个数据集生效」，将选中的 `dataSet.id` 写入 `source_dataset_id`；
        - 若保留多选 UI，则使用第一个被选数据集作为精确过滤值，其余仅展示但不参与请求（需要在文案中提示）。
  - **场景类型（模糊匹配）**
    - 绑定字段：`scenario_type`；
    - 输入控件：`el-input`，placeholder 参考 Step02 页面的「场景类型（包含）」。
  - **子场景类型（模糊匹配）**
    - 绑定字段：`sub_scenario_type`；
    - 输入控件：`el-input`，placeholder 参考 Step02 页面的「子场景类型（包含）」。
  - **执行状态（默认值为「成功」）**
    - 绑定字段：`status`；
    - 控件：`el-select`，枚举值沿用 Step02：
      - `init / processing / success / failed`；
    - 默认值：组件 `setup` 中初始化 `queryStatus` 为 `"success"`，`onMounted` 时自动触发一次列表加载。
  - **其它查询字段**
    - 参考现有 Step02 数据清洗管理的查询字段，在上述四个条件之后依次排列：
      - `scenario_description`（场景描述，包含匹配）；
      - `rewritten_question`（改写后问题）；
      - `rewritten_answer`（改写后回答）；
      - `rewritten_rule`（改写后规则）；
      - `source_item_id`（来源 dataItemsId，精确）；
      - `batch_code`（批次 code，包含）；
      - `trace_id`（流程 traceId，包含）。
    - 请求参数命名与 `/data-cleaning/data-items-rewritten` 已有参数保持一致。

- **列表展示区域**
  - **数据接口**：沿用 Step02 的列表接口：
    - `GET /data-cleaning/data-items-rewritten`
    - 分页参数：`limit` / `offset` 逻辑与 Step02 保持一致。
  - **表格列**
    - 表结构完全复用 Step02 `PipelineDataItemsRewrittenComponent` 的数据列：
      - ID、batch_code、source_dataset_id、source_item_id、scenario_type、sub_scenario_type、status、trace_id、场景置信度、AI 评分、人工评分、创建时间、更新时间；
      - 保留「展开行」展示详细文本与元数据。
  - **操作列处理**
    - **不显示操作列**：
      - 不展示「编辑」「再次运行」「删除」等操作按钮；
      - 也不弹出编辑对话框。
    - 前端实现方式：
      - 新组件中仅渲染查询 + 只读表格列；
      - 不引用 `openItemEdit` / `rerunItem` / `deleteItem` 等方法。

### 2.3 批量 Embedding 按钮交互细节

- **点击前校验**
  - 若未选择数据集（`source_dataset_id` 为空）：
    - 弹出 `ElMessage.warning("请先选择数据集后再进行批量 Embedding")`；
    - 不发起请求。
- **请求参数组装**
  - 从当前查询表单中抽取以下字段构造 `query_params`：
    - 必填：`source_dataset_id`；
    - 可选筛选：
      - `scenario_type`、`sub_scenario_type`；
      - `status`（默认为 `"success"`，可由用户切换）；
      - 以及其它 Step02 对应字段（如 `scenario_description` 等）。
  - 请求体结构建议与 Step01 的 `rewritten/execute` 一致，便于后端复用模板：
    - `POST /data-cleaning/embedding-batches/execute`
    - Body 示例：
      - `{ "query_params": { "source_dataset_id": "...", "scenario_type": "...", "sub_scenario_type": "...", "status": "success", ... } }`

- **结果展示**
  - 成功场景：
    - 通知文案中包含：
      - `batch_code`；
      - 创建的任务总数 `total`；
      - 提示「Embedding 将异步执行，可在后续的 Embedding 批次或任务监控界面查看执行进度」。
  - 失败场景：
    - 统一从后端 `message` 或 `detail` 中取文案展示。

---

## 3. 后端接口依赖（已迁移至通用批次接口方案）

> 说明：本节原本设计的是 Embedding 专用创建接口（`POST /data-cleaning/embedding-batches/execute`）及其 Schemas/Domain 实现，  
> 这些内容已在 `022703-批次任务通用创建接口技术设计.md` 中被 **通用批次接口方案** 替代。  
> 本文件仅保留 **前端对后端的依赖约定**，具体技术设计以 `022703` 为准。

### 3.1 前端调用的后端接口

- **统一入口**：  
  - `POST /api/v1/batch-jobs/create`
- **请求体结构**：  
  - 前端在点击「批量Embedding」时，需要按如下结构发起请求：
    - ```json
      {
        "job_type": "pipeline_embedding",
        "query_params": {
          "source_dataset_id": "...",          // 必填，来源 DataSetsId，精确匹配
          "scenario_type": "...",              // 可选，包含匹配
          "sub_scenario_type": "...",          // 可选，包含匹配
          "status": "success",                 // 可选，默认 success，枚举 init/processing/success/failed
          "scenario_description": "...",       // 可选，包含匹配
          "rewritten_question": "...",         // 可选，包含匹配
          "rewritten_answer": "...",           // 可选，包含匹配
          "rewritten_rule": "...",             // 可选，包含匹配
          "source_item_id": "...",             // 可选，精确匹配
          "batch_code": "...",                 // 可选，包含匹配
          "trace_id": "..."                    // 可选，包含匹配
        }
      }
      ```
  - 其中 `query_params` 字段与本文件第 2.2 节中 Step03 查询区域的表单字段一一对应。

- **响应体结构**：  
  - 接口返回通用批次创建响应，前端只依赖以下字段：
    - `success: bool`：是否创建成功；
    - `message: str`：提示信息；
    - `batch_code: str`：批次编码（用于展示与后续追踪）；
    - `total: int`：本次批次创建的子任务数量。
  - 实际返回中还会包含 `job_type: str`（如 `"pipeline_embedding"`），可按需用于调试或日志，不是 Step03 页面必需字段。

### 3.2 后端实现位置（供排查参考）

- **API 层**：  
  - 路由：`backend/app/api/routes/batch_jobs.py`  
  - Schema：`backend/app/api/schemas/batch_jobs.py`（`BatchJobCreateRequest` / `BatchJobCreateResponse`）
- **Service 层**：  
  - 批次创建服务：`backend/domain/batch/batch_job_service.py`（`BatchJobCreateService`）  
  - 通过 `job_type="pipeline_embedding"` 路由到对应 Handler。
- **Domain & Repository 层**：  
  - Embedding 批次 Handler：`backend/domain/batch/pipeline_embedding_batch_handler.py`  
  - 改写后数据仓储扩展：`backend/infrastructure/database/repository/data_items_rewritten_repository.py` 中的 `get_all_for_embedding`。

> 若需要查看批次任务创建的完整技术方案（包括 Handler 映射、任务表结构、执行器对接等），  
> 请以 `022703-批次任务通用创建接口技术设计.md` 为准，不再在本文件中重复。

---

## 4. 开发进度

- 2026-02-27：  
  - **后端**：已按照 `022703-批次任务通用创建接口技术设计.md` 完成通用批次创建接口及 `pipeline_embedding` 相关 Handler，实现了本文件中 Step03 所需的批量 Embedding 创建能力。  
  - **前端**：已基于本清单完成 Step03 页面实现：  
    - 在 `data-cleaning.html` 中新增菜单项「Step03批量创建Embedding」，并注册 `PipelineEmbeddingBatchComponent`；  
    - 新增前端脚本 `frontend/js/pipeline_embedding_batches.js`，复用 Step02 改写后数据列表作为数据源，提供查询表单与「批量Embedding」按钮；  
    - 按本节约定调用 `POST /api/v1/batch-jobs/create` 接口，封装 `job_type="pipeline_embedding"` 与当前查询条件 `query_params`，并展示返回的 `batch_code` 与 `total`。
