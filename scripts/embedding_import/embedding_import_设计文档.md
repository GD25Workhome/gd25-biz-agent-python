# Embedding 导入脚本设计文档

## 一、目标与范围

### 1.1 目标

编写独立启动脚本，从 `blood_pressure_session_records` 表中读取原始数据，按条组装为流程所需的状态与配置，调用 `embedding_agent` 流程执行词干提取 → 加工 → Embedding → 入库，用于批量生成 RAG 向量数据。

### 1.2 范围

- **数据源**：`backend/infrastructure/database/models/blood_pressure_session.py` 对应表
- **流程**：`config/flows/embedding_agent/flow.yaml`（`embedding_agent`）
- **参考实现**：`backend/app/api/routes/chat.py` 的组装与调用逻辑（约 53–82 行），仅做流程 invoke，不做 Chat 响应解析、last AI 消息提取等

### 1.3 执行流程概览

```
查询表数据(limit N) → 逐条组装 state + config → RuntimeContext + Langfuse → graph.ainvoke → 下一条
```

---

## 二、流程图的获取方式（与 Chat 的差异）

### 2.1 Chat 的获取方式

- `get_flow_graph(session_id)`：从 `ContextManager` 取 `session_context`，再取 `flow_info.flow_key`，最后 `FlowManager.get_flow(flow_key)`。
- 依赖登录生成的 Session，且 flow 由 Session 绑定。

### 2.2 脚本的获取方式（设计要点）

**不依赖 Session，直接编译并获取指定流程：**

1. 保证项目根目录、环境、配置已正确加载（与 `import_blood_pressure_session_data` 等脚本一致）。
2. 调用 `FlowManager.scan_flows()`，确保 `embedding_agent` 在 `_flow_definitions` 中（若已扫描可跳过）。
3. 使用 **固定 flow_key**：`embedding_agent`（与 `flow.yaml` 的 `name` 一致）。
4. 通过 `FlowManager.get_flow("embedding_agent")` 获取编译后的 `CompiledGraph`。
5. **不**使用 `get_flow_graph(session_id)`，不访问 `ContextManager` 的 Session/Token 缓存。

### 2.3 小结

| 项目       | Chat API                    | 本脚本                         |
|------------|-----------------------------|--------------------------------|
| 流程图来源 | Session → flow_key → 取图   | 直接 `FlowManager.get_flow("embedding_agent")` |
| 依赖       | 登录、Session、Token        | 无                             |

---

## 三、状态（State）的初始化逻辑

### 3.1 与 Chat 的对应关系

Chat 中（`helpers.py`）：

- `build_history_messages(request.conversation_history)` → `history_messages`
- `build_current_message(request.message)` → `current_message`
- `build_initial_state(...)` → `FlowState`（含 `prompt_vars` 等）

脚本 **不再** 使用 `ChatRequest`，而是 **从表记录** 映射为等价的 `FlowState` 字段。

### 3.2 表字段与 State 的映射

| State 字段         | 来源 | 说明 |
|--------------------|------|------|
| `current_message`  | `BloodPressureSessionRecord.new_session` | `HumanMessage(content=new_session)`，即「最新发言」 |
| `history_messages` | `history_session` + `history_response`   | 见 3.3 |
| `flow_msgs`        | —    | 初始化为 `[]` |
| `session_id`       | 脚本生成 | 建议 `embedding_import_{record.id}` 或直接用 `record.id`，保证每条唯一 |
| `token_id`         | 脚本生成 | 批量场景无真实 Token，可用占位符如 `embedding_import`；若后续有工具用 `get_token_id()`，须在设计中考虑 |
| `trace_id`         | **每条新生成** | 见 3.5 |
| `prompt_vars`      | 见表记录 | 见 3.4 |

### 3.3 `history_messages` 的解析（重要）

- 表中：`history_session`（历史用户发言）、`history_response`（历史助手回复），均为 Text。
- 流程中：`stem_extraction_node` 的 prompt（`20-ext_agent.md`）使用「历史聊天记录」；Agent 节点将 `history_messages` + `current_message` 作为输入消息列表。
- 实现解析函数 `parse_history_messages(record) -> List[BaseMessage]`，输出 `HumanMessage` / `AIMessage` 的列表（案例一为严格交替；案例二按轮对齐，某轮缺提问或缺响应时仅输出对应单条）；解析失败时退化为 `[]` 并打日志，不中断脚本。

**格式约定**：当前存在两种存储格式，需根据内容自动判断并分别解析。

---

#### 案例一：会话和响应在一起（Q/A 交替）

**形态**：同一段文本内，用户与助手内容以 `Q：` / `A：` 交替出现，多轮之间可有 `------` 等分隔行。

**示例**：

```text
Q：小悦您好！我想约龙医生，做造影
A：您有和医生提前预约吗？
Q：没有
A：了解了，方便告知下患者就诊姓名、诊疗卡号、住院时间、具体什么情况吗？
------
```

**解析规则**：

- 按行遍历；空白行、仅包含 `-` 的分隔行（如 `------`、`--------`）忽略。
- 行首为 `Q：` 或 `Q:`（全角/半角）→ 该行剩余内容为一条用户发言，追加 `HumanMessage(content=...)`。
- 行首为 `A：` 或 `A:` → 该行剩余内容为一条助手回复，追加 `AIMessage(content=...)`。
- 非 Q/A 行：可约定视为延续上一条消息（追加到上一条的 `content`），或忽略；**建议先实现「严格 Q/A 行」**，非 Q/A 行忽略并打 debug 日志。
- 数据来源：若该格式存在于 `history_session` 且 `history_response` 为空，则仅解析 `history_session`；若两者均非空，需与数据导入方确认是否合并后再解析，暂定**仅解析 `history_session`**。

**输出**：按出现顺序的 `[HumanMessage, AIMessage, HumanMessage, AIMessage, ...]`。

---

#### 案例二：会话和响应不在一起（分轮存储）

**形态**：`history_session` 中按「第 N 轮提问」分块存储用户发言；`history_response` 中按「第 N 轮响应」分块存储助手回复，且含 `content=...`。

**`history_session` 示例**：

```text
第1轮提问-----------
messageId: c3f30444-25a0-4886-a058-86d7a1447d3f
我刚才做完检查后又挂了心血管内科的医生，说发泡实验阳性3级，建议做手术把小洞补上，想知道我的手麻木症状时这个问题导致的吗
第2轮提问-----------
messageId: 24f7a96b-9a5f-4922-b4cc-3bc6e058d0a5
早上好，今天早上测了127/75/89，我先观察一下吧！谢谢你
```

**`history_response` 示例**：

```text
第1轮响应
content=发泡实验阳性3级提示心脏可能存在卵圆孔未闭（PFO），这种心脏结构异常确实可能与一些神经系统症状有关联。手麻木症状是否由这个问题引起，需要结合麻木的具体特点...

第2轮响应
content=你能主动监测并告诉我血压情况，这个习惯非常棒！这次的血压127/75mmHg已经达到了你135/85mmHg的目标值...
```

**解析规则**：

1. **`history_session`**：
   - 用正则匹配 `第(\d+)轮提问-*` 切分为多块，按轮号排序。
   - 每块内：去掉 `messageId: ...` 行（整行忽略），其余连续非空行拼接为当前轮的用户发言；若无有效内容则该轮用户消息为空字符串。
2. **`history_response`**：
   - 用正则匹配 `第(\d+)轮响应` 切分为多块，按轮号排序。
   - 每块内：定位 `content=`，取等号后至下一轮响应（或结尾）的内容，去除首尾空白；支持多行。若某轮无 `content=`，则该轮助手消息为空字符串。
   - 若块末出现 `articleId=null, articleTitle=null, ...` 等结构化后缀，可保留在 AIMessage 内或按业务需要裁剪；实现时在 `_parse_history_format2` 中统一处理。
3. **对齐**：按轮号 1、2、… 对齐，第 N 轮生成 `HumanMessage(第 N 轮用户发言)`、`AIMessage(第 N 轮助手回复)`，依次追加到结果列表。若某轮仅有提问或仅有响应，仍输出对应单条，避免错位。

**输出**：`[HumanMessage(轮1), AIMessage(轮1), HumanMessage(轮2), AIMessage(轮2), ...]`。

---

#### 格式判别与降级

- **优先按案例二**：若 `history_session` 中包含 `第\d+轮提问` 且 `history_response` 中包含 `第\d+轮响应`，则按**案例二**解析。
- **否则按案例一**：若 `history_session` 中存在 `Q：` / `Q:` / `A：` / `A:` 行，则按**案例一**解析（仅用 `history_session`）。
- **否则**：`history_messages = []`，并打日志（如 `logger.warning("未识别的 history 格式，record_id=...")`），不抛异常。

**实现建议**：`parse_history_messages(record)` 内先做格式判别，再调 `_parse_history_format1(session_text)` 或 `_parse_history_format2(session_text, response_text)`，便于单测与后续扩展。

### 3.4 `prompt_vars` 的组装

`build_system_message` 从 `state["prompt_vars"]` 取占位符替换。`20-ext_agent.md` 涉及：

- `user_info`
- `current_message`（也可由消息列表体现，若 prompt 中单独占位则需提供字符串形式）
- `history_messages`（同上，若 prompt 需要字符串形式）
- `ai_response`
- `manual_ext`
- `current_date`（Chat 里也有）

**从表记录组装**：

| 占位符           | 来源 | 说明 |
|------------------|------|------|
| `current_date`   | `datetime.now().strftime("%Y-%m-%d %H:%M:%S")` | 同 Chat |
| `user_info`      | `age`、`disease`、`blood_pressure`、`symptom`、`medication`、`medication_status`、`habit` 等 | 建议结构化为字典或约定格式字符串，与 `UserInfo.get_user_info()` 或 prompt 示例保持一致 |
| `ai_response`    | `new_session_response` | 即「回复内容」 |
| `manual_ext`     | `ext` | 人工标记等，空则 `""` |
| `current_message` / `history_messages` | 若 prompt 模板中单独使用 | 用 `current_message.content`、以及 `history_messages` 的格式化字符串（如 "用户: ...\n助手: ..."） |

具体键名以 `20-ext_agent.md` 中 `{...}` 为准；若已有 `build_initial_state` 的 `prompt_vars` 结构，尽量复用同一结构，仅数据源改为表字段。

### 3.5 `trace_id` 规则（设计要点）

- **每条记录** 调用流程前 **重新生成** 一个 `trace_id`。
- **禁止** 同一批次多条记录共用同一个 `trace_id`。
- 生成方式：`uuid.uuid4().hex` 或 `secrets.token_hex(16)`，即 32 位小写十六进制，满足 Langfuse 要求（若项目有 `normalize_langfuse_trace_id`，可复用）。

---

## 四、Langfuse 与 RuntimeContext

### 4.1 Langfuse Handler（设计要点）

- **保留** 与 Chat 相同的 Langfuse 集成方式，便于在服务器上通过 Langfuse 排查问题。
- 每条记录 invoke 前：
  - 生成该条的 `trace_id`（见 3.5）；
  - 调用 `create_langfuse_handler(context={"trace_id": trace_id})`；
  - 若返回非 `None`，则将该 handler 放入 `config["callbacks"]`，再调用 `graph.ainvoke`。
- 若 Langfuse 要求「先创建 Trace 再关联」：在 `create_langfuse_handler` 之前，对该条的 `trace_id` 调用 `set_langfuse_trace_context(name="embedding_import", trace_id=trace_id, session_id=..., metadata={"record_id": record.id})`，再传入相同 `trace_id` 创建 handler。是否必要，以项目现有 Langfuse 集成方式为准。

### 4.2 RuntimeContext

- 与 Chat 一致，在 `ainvoke` 前进入 `RuntimeContext`：
  - `token_id`：占位符（如 `embedding_import`）或按 3.2 约定；
  - `session_id`：同 `state["session_id"]`（每条不同）；
  - `trace_id`：本条刚生成的 `trace_id`。
- 确保流程内工具若使用 `get_token_id()` / `get_session_id()` / `get_trace_id()` 能拿到脚本注入的值，且 `trace_id` 与 Langfuse 使用同源。

---

## 五、配置与 Invoke 参数

### 5.1 `config` 结构

- `configurable.thread_id`：与 `state["session_id"]` 一致，**每条记录不同**，避免 LangGraph checkpoint 串线。
- `callbacks`：即 `[langfuse_handler]`（当 handler 存在时），逻辑同 `chat.py` 77–78 行。

### 5.2 调用方式

```text
with RuntimeContext(token_id=..., session_id=..., trace_id=...):
    config = {"configurable": {"thread_id": session_id}}
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
    result = await graph.ainvoke(initial_state, config)
```

- 不解析 `result` 中的 `flow_msgs`、last AI 消息等；仅完成流程执行。
- 可根据需要打日志（如 `record.id`、`trace_id`、成功/失败），或做简单统计（成功数、失败数）。

---

## 六、数据读取与批次控制

### 6.1 查询与 `batch_size`

- 表：`BloodPressureSessionRecord` 对应表。
- **`batch_size`**：单次查询条数（`LIMIT batch_size`），可加 `ORDER BY created_at` 等保证可重复性。
  - **默认值**：若不通过 CLI 或环境变量指定，**代码中写死默认值 `5`**（测试阶段常用）。
  - 可选：支持 `--limit` 或环境变量覆盖，实现时在入口解析后传入。

### 6.2 数据库与环境

- 复用 `import_blood_pressure_session_data` 的数据库连接方式（如 `ensure_psycopg3_sync_url`、`create_engine`、`sessionmaker`）。
- 脚本入口需将项目根加入 `sys.path`，并加载 `backend.app.config.settings` 等，与现有脚本一致。

### 6.3 异步与同步

- 流程执行使用 `await graph.ainvoke(...)`，脚本须在 async 入口运行（如 `asyncio.run(main())`）。
- 读表为同步 SQLAlchemy；若后续改为异步引擎，再相应调整。

---

## 七、其他注意事项与可扩展点

### 7.1 已覆盖的设计要点

1. **流程图**：脚本自行编译流程图并 `get_flow("embedding_agent")`，不依赖 Session。
2. **State 初始化**：从表字段映射 `current_message`、`history_messages`、`prompt_vars` 等；`history_messages` 需明确解析规则并实现。
3. **trace_id**：每条重新生成，绝不整批复用。
4. **Langfuse**：保留 `create_langfuse_handler`，便于服务器端日志与排查。

### 7.2 建议补充的实现细节

- **错误处理**：单条记录组装或 invoke 失败时，记录日志并继续下一条；最后汇总成功/失败条数。
- **幂等与断点续跑**：若后续需要「跳过已嵌入」等，可考虑在表中或外围存储记录已处理 `id`，本设计可先不做，在文档中留扩展说明。
- **before_embedding_func / insert_data_to_vector_db**：若这些 function 节点使用 `get_token_id()` 等，当前用占位 `token_id` 时的行为需在实现时验证；若有写库、写向量库逻辑，要明确使用哪些标识（如 `record.id`、`message_id`）做关联或去重。
- **日志**：建议每条至少打印 `record.id`、`trace_id`、成功/失败；便于与 Langfuse 对照。

### 7.3 依赖与入口

- 依赖：与 `backend` 及现有脚本相同（如 `langchain`、`langfuse`、`sqlalchemy`、项目内 `backend.*` 等）。
- 入口：`python scripts/embedding_import/run_embedding_import.py`；可选支持 `--limit`（覆盖 `batch_size`）、`--dry-run` 等参数。

---

## 八、代码结构

### 8.1 目录布局

```
scripts/embedding_import/
├── run_embedding_import.py    # 脚本入口（唯一可直接执行的 .py）
├── embedding_import_设计文档.md
└── core/                      # 工具方法、类所在子包
    ├── __init__.py
    ├── config.py              # 常量与默认配置
    ├── history_parser.py      # 历史会话解析
    ├── state_builder.py       # 从表记录组装 FlowState / prompt_vars
    ├── repository.py          # 数据库查询
    └── runner.py              # 单条执行与批次调度（可选，亦可放在入口）
```

- **入口**：仅 `run_embedding_import.py`，负责 CLI、`asyncio.run(main())`、加载配置、取图、查表、循环调 `core` 执行。
- **工具与类**：全部放在 `core/` 下，便于单测与复用。

### 8.2 脚本入口 `run_embedding_import.py`

| 职责 | 说明 |
|------|------|
| 项目根与路径 | 与 `import_blood_pressure_session_data` 一致，将项目根加入 `sys.path`，确保可 `import backend.*`。 |
| CLI | 解析 `--limit`（覆盖 `batch_size`）、`--dry-run` 等；未传 `--limit` 时使用 **默认 `batch_size = 5`**（见 8.3）。 |
| 主流程 | `async def main()`：拉取流程 `FlowManager.get_flow("embedding_agent")`、`repository.fetch_records(limit)`、逐条 `runner.run_one(record, graph)`（或等价位），统计成功/失败、打日志。 |
| 异步入口 | `if __name__ == "__main__": asyncio.run(main())`。 |

### 8.3 `core/config.py` — 常量与默认配置

| 名称 | 类型 | 说明 |
|------|------|------|
| `DEFAULT_BATCH_SIZE` | `int` | **默认批量大小，值为 `5`**。入口在未指定 `--limit` 时使用。 |
| `FLOW_KEY` | `str` | 流程名，`"embedding_agent"`。 |
| `TOKEN_ID_PLACEHOLDER` | `str` | 批量脚本占位 `token_id`，如 `"embedding_import"`。 |
| `SESSION_ID_PREFIX` | `str` | 可选，如 `"embedding_import_"`，用于生成 `session_id`。 |

### 8.4 `core/history_parser.py` — 历史会话解析

| 方法 | 签名 | 说明 |
|------|------|------|
| `parse_history_messages` | `(record: BloodPressureSessionRecord) -> List[BaseMessage]` | 格式判别后调用 format1/format2；解析失败返回 `[]` 并打日志。 |
| `_parse_history_format1` | `(session_text: str) -> List[BaseMessage]` | 案例一：Q/A 交替，仅 `history_session`。 |
| `_parse_history_format2` | `(session_text: str, response_text: str) -> List[BaseMessage]` | 案例二：第 N 轮提问 / 响应分块、对齐。 |
| `_detect_format` | `(session_text: Optional[str], response_text: Optional[str]) -> Literal["format1", "format2", "unknown"]` | 根据 3.3 节规则判别格式。 |

### 8.5 `core/state_builder.py` — 从表记录组装 State

| 方法 | 签名 | 说明 |
|------|------|------|
| `build_initial_state_from_record` | `(record, session_id: str, trace_id: str) -> FlowState` | 根据 3.2、3.4 组装完整 `FlowState`（含 `current_message`、`history_messages`、`prompt_vars`、`flow_msgs`、`token_id` 等）；内部调 `parse_history_messages`、`build_prompt_vars_from_record`。 |
| `build_prompt_vars_from_record` | `(record) -> Dict[str, Any]` | 从表字段组装 `prompt_vars`（`user_info`、`current_date`、`ai_response`、`manual_ext` 等），供 `build_initial_state_from_record` 使用。 |

### 8.6 `core/repository.py` — 数据库查询

| 方法 | 签名 | 说明 |
|------|------|------|
| `fetch_records` | `(limit: int, offset: int = 0) -> List[BloodPressureSessionRecord]` | 查询表，`ORDER BY created_at`，`LIMIT limit OFFSET offset`；复用 `import_blood_pressure_session_data` 的引擎 / `sessionmaker`、`ensure_psycopg3_sync_url` 等。 |
| `get_db_session` | `() -> Session` | 返回同步 SQLAlchemy `Session`（或工厂），供 `fetch_records` 使用。 |

### 8.7 `core/runner.py` — 单条执行与批次逻辑

| 方法 | 签名 | 说明 |
|------|------|------|
| `run_one` | `async (record, graph, *, dry_run: bool = False) -> bool` | 对单条记录：生成 `trace_id`、`session_id`，`state_builder.build_initial_state_from_record`，`RuntimeContext` + `create_langfuse_handler`，`graph.ainvoke`；成功返回 `True`，否则 `False` 并打日志。`dry_run` 时仅组装 state、不 invoke。 |
| `run_batch` | `async (records, graph, *, dry_run: bool = False) -> Tuple[int, int]` | 逐条 `run_one`，汇总成功数、失败数并返回；可选在入口直接循环调 `run_one` 替代。 |

### 8.8 小结

- **`batch_size`**：代码默认 `5`，可通过 `--limit` 覆盖。
- **入口**：`run_embedding_import.py`；**工具与类**：`core` 子包（`config`、`history_parser`、`state_builder`、`repository`、`runner`）。
- 实现时按本节模块划分即可，便于单测与后续扩展。

---

## 九、小结

| 模块           | 处理方式 |
|----------------|----------|
| 流程图         | `FlowManager.get_flow("embedding_agent")`，不依赖 Session |
| State          | 从表记录映射；`history_messages` 需解析规则 + 实现 |
| trace_id       | 每条新生成，不重用 |
| Langfuse       | `create_langfuse_handler` + `config["callbacks"]`，与 Chat 一致 |
| RuntimeContext | `token_id` / `session_id` / `trace_id` 每条设置后 `ainvoke` |
| 数据读取       | 表查询，默认 `batch_size=5`，可 `--limit` 覆盖 |
| 调用           | 仅 `graph.ainvoke`，不做 Chat 响应解析 |

按上述设计实现脚本后，即可从 `blood_pressure_session_records` 读表，按条组装并跑通 `embedding_agent` 流程，同时保留 Langfuse 追踪与日志能力。

---

## 十、开发进度

### 10.1 已完成

| 任务 | 状态 | 说明 |
|------|------|------|
| core/config.py | ✅ 已完成 | 常量与默认配置（DEFAULT_BATCH_SIZE=5、FLOW_KEY、TOKEN_ID_PLACEHOLDER、SESSION_ID_PREFIX） |
| core/history_parser.py | ✅ 已完成 | 案例一 Q/A、案例二 第N轮 解析；`parse_history_messages`、`_detect_format`、`_parse_history_format1`、`_parse_history_format2` |
| core/state_builder.py | ✅ 已完成 | `build_initial_state_from_record`、`build_prompt_vars_from_record` |
| core/repository.py | ✅ 已完成 | `fetch_records`、`get_db_session`；复用 ensure_psycopg3_sync_url、settings.DB_URI |
| core/runner.py | ✅ 已完成 | `run_one`、`run_batch`；trace_id 每条新生成，RuntimeContext + Langfuse |
| run_embedding_import.py | ✅ 已完成 | 入口脚本；CLI `--limit`、`--dry-run`；默认 batch_size=5 |
| 单测 | ✅ 已完成 | `cursor_test/test_embedding_import_history_parser.py`（9 用例）、`cursor_test/test_embedding_import_state_builder.py`（2 用例），均通过 |

### 10.2 运行与验证

- **单测**：  
  `pytest cursor_test/test_embedding_import_history_parser.py cursor_test/test_embedding_import_state_builder.py -v`
- **入口脚本**：  
  `python scripts/embedding_import/run_embedding_import.py [--limit N] [--dry-run]`  
  依赖项目环境（DB、FlowManager、embedding_agent 流程等）。若本机未配置 DB 或流程依赖（如 `langchain`、`pgvector` 等），运行入口脚本可能报错；单测不依赖 DB，可直接跑通。

### 10.3 未完成 / 后续可选

- 无。核心功能已按设计实现。  
- 可选：在实际具备 DB 与流程环境后，跑通 `run_embedding_import.py --dry-run --limit 1` 做端到端验证。
