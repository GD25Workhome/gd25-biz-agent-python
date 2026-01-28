# create_rag_data_batch_func 设计文档（基于 function 节点的方案）

## 1. 背景与目标

在 `012805-create_rag_data脚本Langfuse对接迭代方案.md` 中，我们给出了两类方案：

- 方案一：脚本侧直接对接 Langfuse（已设计完毕，改造成本低）；
- 方案二：**流程内 function 节点封装脚本逻辑**（本文件重点细化）。

本设计文档专注于**方案二**：实现一个 `function` 节点（暂命名为 `create_rag_data_batch_func`），在 LangGraph 流程内完成：

- 批量遍历 QA 场景 md 文件；
- 对每个 md 调用 `create_rag_agent` 单节点子流程或 agent 节点；
- 解析模型返回 JSON；
- 写入 `knowledge_base` 数据库表（含 `source_meta`、`raw_material_full_text` 等字段）；
- 与 Langfuse 对接（可选父 trace + 每文件子 span）。

脚本 `run_create_rag_data.py` 最终可以简化为「只调一次 batch flow」，所有批处理逻辑收敛到 flow 的 function 节点内部。

## 2. 总体架构

### 2.1 新增 function 节点实现

- **类名**：`CreateRagDataBatchFuncNode`  
- **所在模块**：`backend/domain/flows/implementations/create_rag_data_batch_func.py`  
- **继承关系**：`BaseFunctionNode`  
- **function_key**：`"create_rag_data_batch"`（通过 `get_key()` 返回，用于 flow.yaml 中的 `function_key` 绑定）。

职责：

1. 从配置或 state 中获取**场景记录目录**、**白名单/包含文件列表**、**最大并发数**等批处理参数；
2. 扫描 md 文件列表（或直接使用传入列表）；
3. 对每个文件：
   - 读取全文作为 `scene_record_content`；
   - 调用 `create_rag_agent` 子流程或 agent 节点，得到模型输出文本；
   - 解析为 `cases` 数组（沿用 `scripts/create_rag_data/core/parser.py` 的逻辑）；
   - 调用仓储逻辑，逐条写入 `knowledge_base`（含 `source_meta`、`raw_material_full_text` 等字段）；
   - 在需要时与 Langfuse 对接（每文件一个 trace/span）。
4. 统计成功/失败文件数与总写入条数，记录到日志及 state（如 `edges_var["batch_stats"]`）。

### 2.2 新增批处理 flow（Batch Flow）

建议新建一个**专用批处理流程**，与 embedding_agent、medical_agent 等流程解耦：

- **目录**：`config/flows/create_rag_data_batch/`  
  - `flow.yaml`  
  - （必要时）其它 prompts/文案

示例结构：

```yaml
name: create_rag_data_batch
version: "1.0"
description: "QA 场景独立记录批处理导入知识库（function 节点）"

nodes:
  - name: create_rag_data_batch_node
    type: function
    config:
      function_key: "create_rag_data_batch"
      # 下列配置由 function 节点读取
      scene_records_dir: "cursor_docs/012802-QA场景独立记录"
      include_files: []              # 为空=全部；可配置 ["01-xxx.md", ...]
      create_rag_agent_flow_key: "create_rag_agent"
      max_concurrent: 3

edges:
  - from: create_rag_data_batch_node
    to: END
    condition: always

entry_node: create_rag_data_batch_node
```

> 说明：  
> - `create_rag_agent_flow_key` 指向已有的单节点流程 `config/flows/create_rag_agent/flow.yaml`；  
> - `scene_records_dir`、`include_files`、`max_concurrent` 都作为**静态配置**写在 flow.yaml 中，便于统一管理；  
> - 若后期需要更精细控制，也可以允许从 state.prompt_vars 覆盖部分配置（例如临时只跑一个文件列表）。

### 2.3 脚本与 flow 的关系

在本方案中，脚本可进一步收缩为：

- `scripts/create_rag_data/run_create_rag_data_batch.py`：  
  - 加载 ProviderManager / FlowManager；  
  - 构建一个最小的初始 state（可只带 `session_id`、`token_id` 等）；  
  - 调用 `FlowManager.get_flow("create_rag_data_batch").ainvoke(initial_state, config)` 一次；  
  - 在 `config` 中传入 Langfuse callbacks / thread_id 等；  
  - 输出 batch 级统计日志。

原有 `run_create_rag_data.py`（逐文件并行）可以：

- 保留作为「脚本侧并行 + 方案一」版本；或  
- 后续迁移为仅作 thin wrapper，调用上述 batch flow。

## 3. CreateRagDataBatchFuncNode 设计细节

### 3.1 配置与输入来源

`CreateRagDataBatchFuncNode` 需要的关键信息来源：

- **Flow 节点 config**（推荐主要来源）：  
  - `scene_records_dir`：场景 md 目录（相对项目根或绝对路径），默认 `cursor_docs/012802-QA场景独立记录`；  
  - `include_files`：白名单列表，空列表/缺省则处理目录下所有 `NN-*.md` 文件；  
  - `create_rag_agent_flow_key`：单文件处理所用子流程名，默认为 `"create_rag_agent"`；  
  - `max_concurrent`：function 节点内部并行度控制（如使用 asyncio.Semaphore）。  

- **state.prompt_vars / edges_var**（可选扩展）：  
  - 若将来需要通过 API / 脚本向 flow 动态传入「本次只跑某几个文件」，可以在 `prompt_vars["include_files"]` 中下发，function 节点优先用 state 中的配置覆盖 flow.yaml 中的默认值。

### 3.2 内部处理流程

伪代码（忽略异常处理与 Langfuse，见 3.3）：\n\n```text
async def execute(self, state: FlowState) -> FlowState:
    # 1. 解析配置（flow.yaml + state 覆盖）
    cfg = self._load_config(state)
    scene_dir = cfg.scene_records_dir
    include_files = cfg.include_files
    flow_key = cfg.create_rag_agent_flow_key
    max_concurrent = cfg.max_concurrent

    # 2. 扫描文件列表
    files = scan_md_files(scene_dir, include_files)

    # 3. 为批次构造父级统计信息
    batch_stats = {\"total_files\": len(files), \"ok_files\": 0, \"fail_files\": 0, \"rows\": 0}

    # 4. 加载子流程图（create_rag_agent）
    graph = FlowManager.get_flow(flow_key)

    # 5. 并行/串行处理每个文件
    sem = asyncio.Semaphore(max_concurrent)
    async def handle_one(path: Path) -> tuple[bool, int]:
        async with sem:
            return await self._process_single_file(path, graph)

    results = await asyncio.gather(*(handle_one(p) for p in files), return_exceptions=True)

    # 6. 汇总结果到 batch_stats，并写回 state.edges_var['batch_stats']
    ...
```\n\n其中 `_process_single_file` 内部逻辑与当前脚本版 `process_one_file` 类似，但挪到了 function 节点中，并增加 Langfuse 对接（3.3）。

### 3.3 Langfuse 对接（function 版）

在 function 节点内部，每处理一个文件时可复用 embedding_import 的 Langfuse 模式：

1. **生成 trace_id / session_id**：  
   - `trace_id = secrets.token_hex(16)`（或调用统一工具）；  
   - `session_id = f\"create_rag_data_batch_{file_id}\"`。

2. **创建 Langfuse CallbackHandler**：  
   - `langfuse_handler = create_langfuse_handler(context={\"trace_id\": trace_id, \"source_file\": rel_path, ...})`；  
   - 若 handler 不为 None，将其放入 `config[\"callbacks\"]`。

3. **构造子流程初始 state**：  
   使用与当前 `flow_runner.build_initial_state` 等价的逻辑，但在这里直接构建：\n\n```python
initial_state: FlowState = {
    \"current_message\": HumanMessage(...),
    \"history_messages\": [],
    \"flow_msgs\": [],
    \"session_id\": session_id,
    \"token_id\": \"create_rag_data_batch\",
    \"trace_id\": trace_id,
    \"prompt_vars\": {},
    \"edges_var\": {
        \"edges_prompt_vars\": {\"scene_record_content\": file_content},
    },
}
```\n\n4. **RuntimeContext**：\n\n```python
from backend.domain.tools.context import RuntimeContext

config = {\"configurable\": {\"thread_id\": session_id}}
if langfuse_handler:
    config[\"callbacks\"] = [langfuse_handler]

with RuntimeContext(token_id=\"create_rag_data_batch\", session_id=session_id, trace_id=trace_id):
    final_state = await graph.ainvoke(initial_state, config)
```\n\n5. **提取模型输出并解析**：  
   - 从 `final_state["flow_msgs"]` 中取最后一条 AIMessage.content；  
   - 走与 `parser.parse_cases_from_model_output` 一致的逻辑解析为 `cases` 数组。

> 若希望「整批一条父 trace + 每文件子 span」，可在 function 节点 `execute()` 最外层使用 `set_langfuse_trace_context` 或 Langfuse 客户端手动创建父 trace，并将 `parent_trace_id` 下发到 `_process_single_file` 作为 context 的一部分（此处只在设计上预留，具体实现可参考项目中已有的 trace 用法）。

### 3.4 写库逻辑复用

为避免与当前脚本版 `repository.save_cases` 重复代码，可选择：

- **方案 A**：将 `scripts/create_rag_data/core/repository.py` 的核心逻辑抽象为可复用函数（例如移动到 `backend/domain/...` 或 `backend/infrastructure/...`），function 节点与脚本均调用该函数；  
- **方案 B**：在 function 节点内部直接实现等价逻辑（`case` → `KnowledgeBaseRecord` 字段 → `session.add(...)`），保持实现与设计文档一致即可。

考虑到批处理 function 节点本身已依赖 `AsyncSession`、`KnowledgeBaseRecord`，**推荐方案 A**，以减小维护成本。

## 4. Flow 及脚本改造建议

### 4.1 Flow 改造

1. **新增批处理 flow**：`config/flows/create_rag_data_batch/flow.yaml`（结构见 2.2）。  
2. 如有需要，也可以在某个「总控」流程中复用该 function 节点，例如：\n\n```yaml
- name: create_rag_data_batch_node
  type: function
  config:
    function_key: \"create_rag_data_batch\"
    scene_records_dir: \"cursor_docs/012802-QA场景独立记录\"
    include_files: []
    create_rag_agent_flow_key: \"create_rag_agent\"
    max_concurrent: 3
```\n\n并在 edges 中从某个上游节点跳转到该节点后 END。

### 4.2 脚本改造

新增一个更薄的入口脚本（可选名称示例）：`scripts/create_rag_data/run_create_rag_data_batch_flow.py`：

- 初始化 path / ProviderManager / Langfuse（父 trace 可选）；  
- 构造 minimal state（可仅含 session_id / token_id / trace_id 等）；  
- `graph = FlowManager.get_flow(\"create_rag_data_batch\")`；  
- `await graph.ainvoke(initial_state, config)`；  
- 打 batch 级统计日志（从 state.edges_var 或 Langfuse 中查看）。

原有 `run_create_rag_data.py` 可继续保留作为「脚本直接并行 + 方案一」版本，二者并存，按场景选择。

## 5. 与现有实现的关系与迁移路径

1. **第一阶段**：保持现有脚本版（方案一）稳定运行，并补齐 Langfuse 对接；  \n2. **第二阶段**：按本设计新增 `CreateRagDataBatchFuncNode` 与 `create_rag_data_batch` flow，先在测试环境跑通；  \n3. **第三阶段**：视使用习惯与运维需要，决定：\n   - 继续使用脚本版为主，batch flow 作为内部复用节点；或\n   - 将线下/定时批处理统一迁到 `create_rag_data_batch` flow，通过更薄的脚本或 flow 调度运行。\n\n这样可以在不影响现有生产路径的前提下，引入 function 节点版本，并逐步过渡到以 flow 为中心的批处理编排。  

