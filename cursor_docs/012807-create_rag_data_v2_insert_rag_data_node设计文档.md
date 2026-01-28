### 背景与目标

本设计文档用于说明 `create_rag_agent` 流程中 `insert_rag_data_node` 节点的技术实现方案，满足以下需求：

- **承接 Agent 节点输出**：在 `config/flows/create_rag_agent/flow.yaml` 中，`insert_rag_data_node` 紧跟在 Agent 节点之后执行，需要从状态中读取 Agent 的结构化输出（`cases` 数组）。
- **批量入库 RAG 知识库**：将 `cases` 数组中的每个元素映射并写入知识库表，一条 case 对应一条表记录。
- **支持批量 & 异步**：在多文件、多场景输入时，利用并发能力加速处理，保证每个文件的多条 case 能够高效入库。
- **可配置化执行**：通过配置控制文件范围、并发度等参数，避免硬编码，便于脚本运行时按需调整。
- **保持与现有脚本风格一致**：整体代码风格参考 `backend/domain/flows/implementations/insert_data_to_vector_db_func.py` 与 `scripts/create_rag_data/run_create_rag_data.py`，但实现逻辑独立于旧版本，不直接引用 `scripts/create_rag_data` 目录下的代码。

---

### 上下文与依赖关系

- **流程配置**：
  - `config/flows/create_rag_agent/flow.yaml:11-12` 定义了执行提示词的 Agent 节点，输出写入 `FlowState`。
  - `config/flows/create_rag_agent/flow.yaml:19-20` 定义 `insert_rag_data_node`，用于将 Agent 输出入库。
- **提示词与输出结构**：
  - `config/flows/create_rag_agent/prompts/create_rag_agent.md:125-126` 中定义了 `"cases": [...]`，模型输出为一个包含多个 case 的数组。
- **字段映射规则**：
  - `cursor_docs/012804-QA场景独立记录转知识库脚本设计.md:102-111` 定义了从模型输出字段到数据库表字段的映射规则，包括数组字段、JSONB 字段与原文追溯信息等。
- **执行入口与批量处理**：
  - `scripts/create_rag_data/run_create_rag_data.py` 提供了批量文件处理与并发执行的实现示例（如使用 `asyncio`、`batch_func` 等）。
  - `scripts/create_rag_data/core/config.py:21` 中通过 `INCLUDE_FILES` 指定文件范围，并通过其他配置控制并发数量。

---

### 新目录与模块结构设计（scripts/create_rag_data_v2）

新版本脚本放在 `scripts/create_rag_data_v2` 目录下，与现有 `scripts/create_rag_data` 并行存在。建议结构如下：

- `scripts/create_rag_data_v2/`
  - `__init__.py`
  - `config.py`
  - `file_loader.py`
  - `parser.py`
  - `repository.py`
  - `flow_runner.py`
  - `run_create_rag_data_v2.py`

各模块职责说明（与 v1 风格类似，但实现独立，下面给出**更细的接口与示例伪代码**，方便后续直接落地实现）：

- **config.py**
  - **核心目标**：集中管理脚本级配置，避免在业务代码中出现硬编码。
  - **主要配置字段（示例）**：
    - `BASE_DIR: Path`：原始 md 文件根目录（例如 `cursor_docs/012802-QA场景独立记录`）。
    - `INCLUDE_FILES: list[str]`：需要处理的文件名称列表（参考 `core/config.py:21`）。
    - `EXCLUDE_FILES: list[str]`：可选，显式排除的文件名。
    - `MAX_CONCURRENCY: int`：并发处理的最大协程数量。
    - `RETRY_TIMES: int`：单文件失败重试次数。
    - `FLOW_KEY: str`：FlowManager 中的流程 key，例如 `"create_rag_agent_v1"`（实际以配置为准）。
    - `DRY_RUN: bool`：是否只跑流程不真正入库（方便联调与回归）。
  - **示例接口设计**：
    - 数据类定义：
      - ```python
        @dataclass
        class CreateRagDataConfig:
            """create_rag_data_v2 脚本运行配置"""
            base_dir: Path
            include_files: list[str]
            exclude_files: list[str]
            max_concurrency: int
            retry_times: int
            flow_key: str
            dry_run: bool = False
        ```
    - 加载函数：
      - ```python
        def load_config() -> CreateRagDataConfig:
            """
            加载脚本运行配置。
            
            优先级：
            1. 环境变量（如 CREATE_RAG_BASE_DIR、CREATE_RAG_MAX_CONCURRENCY 等）
            2. 默认值（如 INCLUDE_FILES = ["01-诊疗-场景1-疾病诊断与费用等.md"]）
            """
            ...
        ```
  - **实现要求**：
    - 所有字段必须有**类型提示**和**中文文档字符串**。
    - 抛出的异常要明确指出是配置错误，便于快速定位。

- **file_loader.py**
  - **核心目标**：根据配置找到需要处理的 md 文件，并将其读入内存。
  - **主要数据结构**：
    - ```python
      @dataclass
      class MarkdownSource:
          """
          单个 Markdown 源文件的信息封装。
          """
          source_path: str      # 相对项目根目录的路径，用于写入 source_meta
          abs_path: Path        # 绝对路径，用于实际读取文件
          raw_markdown: str     # 文件完整内容，用于 raw_material_full_text 与 scene_record_content
      ```
  - **主要函数接口**：
    - `def list_markdown_files(cfg: CreateRagDataConfig) -> list[Path]`：
      - 扫描 `cfg.base_dir` 下的所有 `.md` 文件。
      - 按 `include_files` / `exclude_files` 做过滤。
      - 返回**绝对路径列表**。
    - `def load_markdown(path: Path, project_root: Path) -> MarkdownSource`：
      - 读取单个 md 文件内容。
      - 计算相对路径：`source_path = str(path.relative_to(project_root))`。
      - 返回 `MarkdownSource`。
    - `def load_all_markdowns(cfg: CreateRagDataConfig, project_root: Path) -> list[MarkdownSource]`：
      - 综合使用 `list_markdown_files` 和 `load_markdown`，供入口脚本一次性获取所有源文件。
  - **实现要求**：
    - 对文件不存在、无法读取等情况抛出带中文提示的异常。
    - 使用 UTF-8 读取，避免中文内容乱码。

- **parser.py**
  - **核心目标**：将 Agent 输出的 `cases` 结构安全地转换为知识库表记录对象列表。
  - **建议定义领域数据类**（与 DB Model 解耦，方便测试）：
    - ```python
      @dataclass
      class KnowledgeBaseRecordData:
          """
          知识库记录的领域模型（与数据库模型字段一一对应）。
          """
          scene_summary: str
          optimization_question: Optional[str]
          reply_example_or_rule: Optional[str]
          scene_category: Optional[str]
          input_tags: list[str]
          response_tags: list[str]
          raw_material_full_text: str
          source_meta: dict[str, Any]
      ```
  - **核心解析函数接口**：
    - ```python
      def parse_cases_from_agent_output(
          agent_output: dict[str, Any],
          markdown: MarkdownSource,
      ) -> list[KnowledgeBaseRecordData]:
          """
          将 Agent 输出解析为 KnowledgeBaseRecordData 列表。
          
          参数：
              agent_output: Agent 节点返回的原始 JSON 对象，必须包含 "cases" 字段。
              markdown: 当前处理的 MarkdownSource，用于填充 raw_material_full_text 与 source_meta。
          
          返回：
              转换后的知识库记录列表，一条 case → 一条记录。
          """
      ```
  - **字段映射与容错规则**（对应 `012804-QA场景独立记录转知识库脚本设计.md:102-111`）：
    - `scene_summary`：
      - 必填字段，从单个 case 的 `scene_summary` 读取，若缺失则抛出业务异常。
    - `optimization_question`：
      - 若为数组：`json.dumps(case["optimization_question"], ensure_ascii=False)`。
      - 若为字符串：直接使用该字符串。
      - 若缺失：允许为 `None`。
    - `reply_example_or_rule`：允许为 `None`。
    - `scene_category`：允许为 `None`。
    - `input_tags` / `response_tags`：
      - 若为数组：直接使用。
      - 若为字符串：可选策略是包一层数组 `[value]`。
      - 其他类型：记录告警并降级为 `[]`。
    - `raw_material_full_text`：始终写入 `markdown.raw_markdown`。
    - `source_meta`：始终写入 `{"source_file": markdown.source_path}`。
  - **错误处理细节**：
    - 若 `agent_output` 中缺少 `cases` 或类型不是 `list`：
      - 抛出自定义异常 `InvalidAgentOutputError`，错误信息包含简要的 `agent_output` 摘要。
    - 单个 case 字段缺失时：
      - 视严重程度决定：`scene_summary` 缺失直接报错；非关键字段缺失则记录 warn 日志并填默认值。

- **repository.py**
  - **核心目标**：提供**面向领域数据类**的入库接口，内部封装数据库模型与会话管理。
  - **与基础设施的关系**：
    - 内部通过 `from backend.infrastructure.database.repository.knowledge_base_repository import KnowledgeBaseRepository` 等方式复用已有仓储实现。
    - 不依赖 `scripts/create_rag_data` 目录下的任何模块。
  - **主要接口设计**：
    - ```python
      class KnowledgeBaseWriter:
          """
          知识库写入封装类，负责将领域数据写入数据库。
          """
      
          def __init__(self, repo: KnowledgeBaseRepository) -> None:
              self._repo = repo
      
          async def insert_records(
              self,
              records: list[KnowledgeBaseRecordData],
          ) -> int:
              """
              批量插入知识库记录。
              
              返回成功插入的记录数量。
              """
              ...
      ```
  - **实现要点**：
    - 入库前进行必要的数据校验（例如字符串长度、JSON 字段格式等）。
    - 统一捕获数据库异常，记录错误日志，并抛出带中文信息的业务异常（例如 `KnowledgeBaseWriteError`）。
    - 支持在 dry-run 模式下只记录日志、不真正写库。

- **flow_runner.py**
  - 串联文件读取、Agent 调用、结果解析与入库的主业务流程。
  - 暴露两个重要方法：
    - `async def run_for_single_source(source: MarkdownSource, cfg: CreateRagDataConfig, graph: Any, writer: KnowledgeBaseWriter) -> None`：处理单个 MarkdownSource。
    - `async def run_batch(sources: list[MarkdownSource], cfg: CreateRagDataConfig, graph: Any, writer: KnowledgeBaseWriter) -> tuple[int, int]`：根据配置批量并发处理多个源，返回 `(ok_count, fail_count)`。
  - 内部逻辑参考 `scripts/embedding_import` 实现，而不是直接手工调用 Agent：
    1. **脚本启动时加载配置与流程图**（在 `run_create_rag_data_v2.py` 中完成）：
       - 加载模型供应商配置：参考 `scripts/embedding_import/run_embedding_import.py:66-75`，通过 `ProviderManager.load_providers` 读取 `config/model_providers.yaml`。
       - 加载流程图：参考 `scripts/embedding_import/run_embedding_import.py:77-83`，通过 `FlowManager.get_flow(FLOW_KEY)` 加载 `create_rag_agent` 对应的 Flow。
    2. **读取 md 文件并构造“记录”对象**：
       - 使用 `file_loader` 读取单个 md 文件内容，得到 `raw_markdown` 与 `source_path`。
       - 将每个文件包装为一条「伪记录」，用于替换 `scripts/embedding_import/run_embedding_import.py:86-87` 中数据库记录的角色，即不再从数据库查询 `records`，而是从文件系统构造 `records` 列表。
    3. **批量运行流程图**：
       - `run_batch` 实现示例（伪代码）：
         - ```python
           async def run_batch(
               sources: list[MarkdownSource],
               cfg: CreateRagDataConfig,
               graph: Any,
               writer: KnowledgeBaseWriter,
           ) -> tuple[int, int]:
               """
               并发执行 create_rag_agent 流程。
               
               返回 (成功文件数, 失败文件数)。
               """
               semaphore = asyncio.Semaphore(cfg.max_concurrency)
               ok = 0
               fail = 0
           
               async def _run_one(source: MarkdownSource) -> None:
                   nonlocal ok, fail
                   async with semaphore:
                       try:
                           await run_for_single_source(source, cfg, graph, writer)
                           ok += 1
                       except Exception as e:
                           fail += 1
                           logger.error("处理文件失败: %s, error=%s", source.source_path, e)
               
               tasks = [asyncio.create_task(_run_one(src)) for src in sources]
               await asyncio.gather(*tasks)
               return ok, fail
           ```
       - `run_for_single_source` 内部会复用下文的 state_builder 与 `runner` 逻辑，对单个 MarkdownSource 完成一轮 Flow 调用。
    4. **单条记录的 state 构建与提示词变量填充（对应 state_builder 设计）**：
       - 在 v2 中新增专门的 `state_builder` 模块（文件名建议 `scripts/create_rag_data_v2/state_builder.py`），整体结构参考 `scripts/embedding_import/core/state_builder.py`：
         - 核心函数一：`build_prompt_vars_from_source(source: MarkdownSource) -> Dict[str, Any]`
           - 仅需要构造一个占位符变量 `scene_record_content`：
             - ```python
               def build_prompt_vars_from_source(source: MarkdownSource) -> Dict[str, Any]:
                   """
                   根据 MarkdownSource 构造提示词变量。
                   
                   当前仅包含一个变量：
                       - scene_record_content: md 文件完整内容（必要时可做剪裁）。
                   """
                   return {
                       "scene_record_content": source.raw_markdown,
                   }
               ```
         - 核心函数二：`build_initial_state_from_source(source: MarkdownSource, session_id: str, trace_id: str) -> Dict[str, Any]`
           - 将 `scene_record_content` 等信息塞入初始 FlowState，供 `FlowManager` 使用。
       - 这些变量将映射到 `config/flows/create_rag_agent/prompts/create_rag_agent.md:14-15` 中的占位符：
         - 提示词片段：
           - ```text
             {scene_record_content}
             ```
    5. **入库逻辑的位置**：
       - 与 `embedding_import` 一样，真正的入库逻辑发生在 Flow 内部的 Function 节点（即本设计的 `insert_rag_data_node`），而不是批量 runner 中。
       - `insert_rag_data_node` 从 `state` 中读取 Agent 的输出（包含 `cases`）和文件元信息，调用 `parser` 和 `repository` 完成入库。
    6. **错误处理与统计**：
       - `run_batch` 负责统计每条记录执行成功/失败数量并返回 `ok, fail` 计数。
       - 对于单条记录执行异常，在 runner 内记录错误日志，但不会中断其他记录的执行。

- **run_create_rag_data_v2.py**
  - 作为命令行入口，其整体结构与 `scripts/import_blood_pressure_session_data.py` 保持风格一致：
    - 提供一个同步的 `main()` 函数，负责：
      - 打印脚本标题与关键信息日志。
      - 完成必要的环境与依赖检查（例如项目根目录、配置文件是否存在）。
      - 调用前面所述的「加载模型供应商配置」与「加载流程图」逻辑。
      - 组装批量处理所需的上下文（如待处理 md 文件列表、并发配置等）。
      - 通过 `asyncio.run(flow_runner.run_batch(...))` 启动异步批量处理。
      - 根据运行结果（成功/失败数量）输出汇总日志，并以合适的退出码 `sys.exit(0/1/130)` 结束进程。
    - 顶部使用 `if __name__ == "__main__": main()` 作为脚本入口，不在模块导入阶段执行任何重逻辑。

---

### insert_rag_data_node 实现方案

`insert_rag_data_node` 属于 LangGraph 流中的一个 Function/Tool 节点，其实现代码虽然放在 `scripts/create_rag_data_v2` 目录下进行封装与复用，但最终会在 `backend/domain/flows/implementations` 下以函数形式暴露，供 Flow 配置引用。整体风格参考 `insert_data_to_vector_db_func.py`：

#### 1. 函数签名与类型提示（示意）

> 说明：此处仅为设计示意，实际代码在实现阶段编写。

- 函数名建议：`insert_rag_data_node_func(state: FlowState) -> FlowState`。
- 入参：
  - `state`: `FlowState` 对象，包含上一个 Agent 节点的输出。
- 出参：
  - 更新后的 `FlowState`，可以附加入库结果（如成功数量、失败数量）。

#### 2. 从 state 中读取 Agent 输出（细节）

- Agent 节点输出结构（示例）：
  - ```json
    {
      "cases": [
        {
          "scene_summary": "...",
          "optimization_question": ["...", "..."],
          "reply_example_or_rule": "...",
          "scene_category": "...",
          "input_tags": ["tag1", "tag2"],
          "response_tags": ["tagA"]
        }
      ]
    }
    ```
- `insert_rag_data_node_func` 内部读取路径示例（具体 key 以实际 FlowState 定义为准，可以采用配置或常量）：
  - ```python
    def _extract_cases_from_state(state: FlowState) -> dict[str, Any]:
        """
        从 FlowState 中提取 Agent 节点输出。
        
        约定：
        - Agent 节点的输出挂在 state["create_rag_agent"]["output"] 下，
          或者直接挂在 state["agent_output"] 下（实际以 flow.yaml 为准）。
        """
        try:
            agent_output = state["create_rag_agent"]["output"]
        except KeyError as e:
            raise InvalidAgentOutputError("在状态中未找到 create_rag_agent 输出") from e
        return agent_output
    ```
- 校验逻辑：
  - 确保 `agent_output` 中存在 `cases` 键且类型为 `list`。
  - 若不合法：
    - 记录包含 `session_id` / `source_file` 等上下文信息的错误日志。
    - 抛出 `InvalidAgentOutputError`，中断后续入库。

#### 3. 调用解析与入库逻辑（细节）

1. 从 state 中获取与当前文件相关的元数据：
   - `source_file`：可在初始状态由 `state_builder` 写入，例如 `state["context"]["source_file"]`。
   - `raw_markdown`：可选是否放入 state，若不放，则只在批量脚本层面使用 `MarkdownSource`，在 Flow 内仅依赖 Agent 输出。
   - 设计上推荐：**在 FlowState 中至少记录 `source_file`**，方便 `insert_rag_data_node` 侧写入 `source_meta`。
2. 使用前文定义的 `parse_cases_from_agent_output`：
   - ```python
     def insert_rag_data_node_func(state: FlowState) -> FlowState:
         """
         LangGraph Function 节点：将 Agent 输出写入知识库表。
         """
         logger.info("开始执行 insert_rag_data_node_func 节点")
         
         agent_output = _extract_cases_from_state(state)
         
         # 从 state 中构造 MarkdownSource 兼容数据（至少要有 source_path）
         source_path = state.get("context", {}).get("source_file", "unknown_source")
         markdown_stub = MarkdownSource(
             source_path=source_path,
             abs_path=Path(source_path),   # 这里仅用于类型占位，真正读取在批量脚本中完成
             raw_markdown="",              # 若需要完整原文，可考虑在 state 中传递
         )
         
         records = parse_cases_from_agent_output(agent_output, markdown_stub)
         
         # 调用仓储层写入（此处为同步伪代码，实际可封装为同步接口或在上层以 async 方式调用）
         writer = get_global_knowledge_base_writer()
         inserted_count = writer.insert_records_sync(records)
         
         # 将结果写回 FlowState，方便后续节点或 Langfuse 观测
         state["insert_rag_data_result"] = {
             "inserted": inserted_count,
             "source_file": source_path,
         }
         logger.info("insert_rag_data_node_func 完成, 插入 %d 条记录", inserted_count)
         return state
     ```
3. 在实现时需注意：
   - `insert_rag_data_node_func` 运行环境可能是同步的，因此仓储层可以同时提供同步和异步两个接口（或在内部封装异步执行）。
   - 所有异常都应被清晰日志化，并抛出业务异常，交给 LangGraph / FlowManager 决定重试策略。

---

### 批量与异步处理设计

#### 1. 并发模型

- 采用 `asyncio` 协程与 `asyncio.Semaphore` 控制最大并发度，与现有 `run_create_rag_data.py` 实现风格一致。
- 每个文件对应一个异步任务，任务内部串行执行「Agent 调用 → 解析 → 入库」，保证单文件内的依赖顺序。

#### 2. 错误隔离与重试

- 单文件任务失败时：
  - 记录详细日志（包括文件名、异常堆栈、Agent 原始输出摘要）。
  - 根据配置决定是否进行有限次重试（例如最多重试 2 次，每次间隔固定时间）。
  - 不影响其他文件任务的正常执行。
- 可选：为每条 case 的入库增加细粒度错误处理（例如部分字段异常时跳过该条记录）。

#### 3. 与 FlowState 的关系

- 批量脚本层面：由 `run_create_rag_data_v2.py` + `flow_runner.run_batch` 负责切文件并并发处理。
- 单 Flow 实例内：`insert_rag_data_node_func` 仍然是同步（或单协程）视角，专注于「读取 state → 解析 → 调用 repository」，不直接关心批量与并发，便于在其他场景重用。

---

### 配置化能力设计

参考 `scripts/create_rag_data/core/config.py:21`，在 v2 中提供以下配置项：

- **文件范围控制**
  - `INCLUDE_FILES: list[str]`：只处理列表中的文件。
  - `EXCLUDE_FILES: list[str]`（可选）：显式排除部分文件。
  - `FILE_PATTERN: str`（可选）：支持简单通配符或正则，用于批量选择文件。

- **并发控制**
  - `MAX_CONCURRENCY: int`：最大并发文件数，例如 5 或 10。
  - `RETRY_TIMES: int`：失败重试次数。

- **模型与 Agent 配置**
  - Agent 节点调用方式与 `run_create_rag_data.py` 保持一致：
    - 从 Flow 配置中解析 `prompt` 路径与 `model` 名称。
    - 支持通过环境变量或配置文件覆盖模型 ID。
  - 支持开启或关闭 Langfuse 追踪标记，便于调试。

---

### 异常处理与日志规范

- **异常类型**
  - 配置错误（例如目录不存在、并发数非法）：在启动阶段直接抛出，并给出中文错误提示。
  - Agent 输出格式错误（`cases` 缺失或类型不正确）：抛出业务异常，建议包含文件名与部分原始输出的摘要。
  - 数据库错误：捕获数据库异常并封装为统一的「知识库写入失败」异常，对外暴露易于理解的中文错误信息。

- **日志内容**
  - 每个文件开始与结束处理时记录日志，包含：
    - 文件路径、总 case 数量。
    - 成功入库数量、失败数量。
  - 出错时记录：
    - 文件路径。
    - 异常类型与堆栈。
    - 关键字段值（如 `scene_category`、`scene_summary` 的前若干字符）。

---

### 与现有实现的关系与约束

- **代码风格对齐**：
  - 函数与类均添加完整的类型提示。
  - 文档字符串与注释使用简体中文，说明业务含义与使用方式。
  - 异常信息采用中文，便于排查问题。

- **代码复用约束**：
  - 可以「参考/抄写」`scripts/create_rag_data` 中的实现思路与写法，但不允许直接通过 `import scripts.create_rag_data...` 的方式复用其模块。
  - 若需要通用能力（如数据库连接、Flow 调用工具），优先复用 `backend` 目录下已有的基础设施层模块。

- **向后兼容性**：
  - v1 与 v2 可以并存，v2 主要服务于 `create_rag_agent` 流程和新的知识库表结构。
  - 不对现有使用 v1 的脚本行为产生影响。

---

### 后续实现与测试计划

- **实现步骤建议**
  1. 在 `scripts/create_rag_data_v2` 目录下创建基础模块与空函数骨架。
  2. 参考 `insert_data_to_vector_db_func.py` 与现有 v1 代码，补全 `repository`、`flow_runner` 与入口脚本。
  3. 在 `backend/domain/flows/implementations` 中实现 `insert_rag_data_node_func`，并在 Flow 配置中绑定。
  4. 针对单文件单 case、单文件多 case、多文件多 case 等场景编写单元测试与集成测试。

- **测试重点**
  - `cases` 字段为数组时能正确拆分为多条记录入库。
  - `optimization_question` 为数组和字符串两种情况的兼容处理。
  - `input_tags`、`response_tags` 入库为 JSONB 时结构正确。
  - `raw_material_full_text` 与 `source_meta` 按要求填充，可用于追溯。
  - 并发执行时在大量文件情况下无死锁与严重性能退化。

---

### 进度记录（gd25-plan-start）

| 项目 | 状态 | 说明 |
|------|------|------|
| scripts/create_rag_data_v2 包结构搭建 | 已完成 | 新增 `__init__.py`、`config.py`、`file_loader.py`、`state_builder.py`、`parser.py`、`repository.py`、`flow_runner.py`、`run_create_rag_data_v2.py` |
| create_rag_agent 流批量执行脚本 | 已完成 | `run_create_rag_data_v2.py` 支持按配置加载 Flow、扫描 md 文件并并发执行 |
| insert_rag_data_node 节点实现 | 已完成 | 新增 `backend/domain/flows/implementations/insert_rag_data_func.py`，并在 `__all__` 中注册，function_key 与 flow.yaml 对齐 |
| Agent 输出解析与入库逻辑 | 已完成 | `parser.py` + `KnowledgeBaseWriter`（repository.py），按设计文档字段映射规则实现 |
| 单元测试 | 待补充 | 计划在 `cursor_test` 下新增 parser 与 file_loader 的测试用例，并在实现后通过 pytest 验证 |


