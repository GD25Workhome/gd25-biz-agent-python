# LangGraph 与 Langfuse 集成示例

这是一个轻量化的 LangGraph 与 Langfuse 集成示例，展示了如何：
1. 创建包含两个节点的 LangGraph 流程
2. 集成 Langfuse 进行可观测性追踪
3. 从 .env 文件读取配置

## 功能说明

### 流程结构

```
节点1（普通节点） -> 节点2（Agent节点） -> 结束
```

- **节点1（普通节点）**：处理用户输入，进行简单的文本处理
- **节点2（Agent节点）**：使用 LLM 生成回复

### Langfuse 集成

- 自动创建 Trace 记录整个流程执行
- 自动记录 LLM 调用（通过 CallbackHandler）
- 支持分布式追踪（通过 trace_id）

## 环境配置

### 必需的配置

在项目根目录的 `.env` 文件中配置以下环境变量：

#### Langfuse 配置

```env
# Langfuse 配置（16-18行参考）
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com  # 可选，默认使用 cloud.langfuse.com
```

#### LLM 配置（至少配置一个）

```env
# LLM 配置（29-37行参考）
# 选项1：OpenAI 兼容 API
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1  # 可选
LLM_MODEL=gpt-3.5-turbo  # 可选

# 选项2：豆包 API
DOUBAO_API_KEY=...
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3  # 可选
LLM_MODEL=doubao-seed-1-6-251015  # 可选

# 选项3：DeepSeek API
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1  # 可选
LLM_MODEL=deepseek-chat  # 可选
```

### 配置检查

运行前，请确保以下配置已正确设置：

1. **Langfuse 配置**（如果启用 Langfuse）：
   - ✅ `LANGFUSE_ENABLED=true`
   - ✅ `LANGFUSE_PUBLIC_KEY` 已设置
   - ✅ `LANGFUSE_SECRET_KEY` 已设置
   - ⚠️ `LANGFUSE_HOST`（可选，默认使用 cloud.langfuse.com）

2. **LLM 配置**（至少一个）：
   - ✅ `OPENAI_API_KEY` 或 `DOUBAO_API_KEY` 或 `DEEPSEEK_API_KEY` 已设置

## 运行方式

### 方式1：从项目根目录运行（推荐）

```bash
# 确保在项目根目录
python -m cursor_test.langfuse.03LangChain.test_langgraph_langfuse
```

### 方式2：直接运行脚本

```bash
cd cursor_test/langfuse/03LangChain
python test_langgraph_langfuse.py
```

## 输出说明

### 成功执行输出

```
================================================================================
LangGraph 与 Langfuse 集成示例
================================================================================
[步骤1] 初始化 Langfuse...
Langfuse 客户端初始化成功: host=https://cloud.langfuse.com
[步骤1] Langfuse 初始化成功
[步骤1] 创建 Langfuse Trace: trace_id=...
[步骤2] 构建 LangGraph 图...
[步骤3] 编译 LangGraph 图...
[步骤4] 准备初始状态...
[步骤5] 执行 LangGraph 图...
--------------------------------------------------------------------------------
[节点1] 开始处理输入...
[节点2] 开始生成 Agent 回复...
--------------------------------------------------------------------------------
[步骤5] 图执行完成
[步骤6] 执行结果:
  消息1 (human): 你好，请介绍一下你自己
  消息2 (ai): ...
[步骤7] 刷新 Langfuse 事件...
================================================================================
示例执行完成
Trace ID: ...
请在 Langfuse UI 中查看追踪记录
================================================================================
```

### 无 Langfuse 追踪模式

如果 Langfuse 未启用或配置不完整，程序仍会执行，但不会记录到 Langfuse：

```
[步骤1] Langfuse 未初始化（将跳过 Langfuse 追踪）
[步骤2] 构建 LangGraph 图（无 Langfuse 追踪）...
...
```

## 代码结构

```
test_langgraph_langfuse.py
├── 状态定义
│   └── GraphState: 图状态（包含 messages 和 processed_input）
├── Langfuse 初始化
│   ├── init_langfuse(): 初始化 Langfuse 客户端
│   └── create_langfuse_handler(): 创建 CallbackHandler
├── LLM 客户端创建
│   └── create_llm(): 创建 LLM 客户端（支持多供应商）
├── 节点函数定义
│   ├── node1_process_input(): 节点1 - 处理输入
│   └── node2_agent_response(): 节点2 - Agent 生成回复
├── 图构建
│   └── build_graph(): 构建 LangGraph 图
└── 主函数
    └── main(): 执行流程
```

## 关键实现点

### 1. Langfuse Trace 创建

```python
# 创建 Trace 并使用 context manager
trace = langfuse.trace(
    name="langgraph_langfuse_example",
    user_id="test_user",
    session_id="test_session"
)

with langfuse.start_as_current_span(
    name="main_execution",
    trace_id=trace.id
):
    # 在这个上下文中，所有 CallbackHandler 都会自动关联到此 Trace
    ...
```

### 2. CallbackHandler 使用

```python
# 创建 CallbackHandler
langfuse_handler = create_langfuse_handler()

# 在 LLM 调用时传递
llm.invoke(messages, config={"callbacks": [langfuse_handler]})
```

### 3. 节点执行流程

- **节点1**：同步处理，不涉及 LLM 调用
- **节点2**：异步 LLM 调用，自动记录到 Langfuse

## 常见问题

### Q1: 提示 "Langfuse 配置不完整"

**A**: 检查 `.env` 文件中的配置：
- `LANGFUSE_ENABLED=true`
- `LANGFUSE_PUBLIC_KEY` 和 `LANGFUSE_SECRET_KEY` 都已设置

### Q2: 提示 "未配置 LLM API Key"

**A**: 在 `.env` 文件中至少配置一个 LLM API Key：
- `OPENAI_API_KEY` 或
- `DOUBAO_API_KEY` 或
- `DEEPSEEK_API_KEY`

### Q3: 如何在 Langfuse UI 中查看追踪记录？

**A**: 
1. 访问 Langfuse UI（根据 `LANGFUSE_HOST` 配置）
2. 查找名为 "langgraph_langfuse_example" 的 Trace
3. 查看详细的执行链路和 LLM 调用记录

### Q4: 如何修改流程或添加更多节点？

**A**: 
1. 在 `build_graph()` 函数中添加新节点
2. 定义对应的节点函数
3. 使用 `graph.add_node()` 和 `graph.add_edge()` 连接节点

## 参考文档

- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [Langfuse LangChain 集成文档](https://langfuse.com/integrations/frameworks/langchain)
- [LangChain 回调机制文档](https://python.langchain.com/docs/modules/callbacks/)

## 注意事项

1. **环境变量加载**：项目使用 `pydantic_settings` 自动从 `.env` 文件加载配置，确保 `.env` 文件在项目根目录
2. **Langfuse 版本**：本示例使用 Langfuse SDK v3.x，如果使用 v2.x 需要调整代码
3. **LLM 供应商**：支持所有兼容 OpenAI API 格式的供应商（通过 `ChatOpenAI` 统一接口）

