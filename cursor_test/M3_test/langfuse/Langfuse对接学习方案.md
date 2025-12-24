# Langfuse 对接学习方案

## 📋 目标

通过逐步的单元测试，学习如何在 LangGraph 项目中集成 Langfuse，实现：
1. 追踪 LangGraph 的执行链路
2. 记录 LLM 调用详情（输入、输出、tokens 等）
3. 在 Langfuse Dashboard 中查看和分析执行流程
4. 为后续生产环境集成做准备

## 🎯 学习路径

### 阶段一：基础对接（测试 1-2）
**目标**：理解 Langfuse 的基本用法，验证环境配置

- **测试 1**：最简单的 LangGraph 调用（无 LLM）
  - 验证 Langfuse 环境配置
  - 验证 Trace 和 Span 的基本追踪
  - 验证在 Dashboard 中能看到执行流程

- **测试 2**：带 LLM 调用的简单 LangGraph
  - 验证 LLM 调用被正确追踪
  - 验证输入/输出、tokens 等信息被记录
  - 验证 Generation 类型的 Span

### 阶段二：项目集成（测试 3-4）
**目标**：在项目实际代码中集成 Langfuse

- **测试 3**：使用项目中的路由图（简化版）
  - 使用 `create_router_graph` 创建图
  - 验证多个节点的追踪
  - 验证条件路由的追踪

- **测试 4**：完整的路由图调用（模拟真实场景）
  - 模拟完整的聊天请求
  - 验证多轮对话的追踪
  - 验证用户 ID、会话 ID 等元数据

## 📝 测试用例设计

### 测试 1：最简单的 LangGraph 调用（无 LLM）

**目的**：
- 验证 Langfuse 环境配置正确
- 验证基本的 Trace 和 Span 追踪
- 验证在 Dashboard 中能看到执行流程

**测试内容**：
```python
# 创建一个简单的 LangGraph，包含 2-3 个节点
# 节点不调用 LLM，只做简单的数据处理
# 使用 LangfuseCallbackHandler 追踪
# 验证：
# 1. Trace 被创建
# 2. 每个节点作为 Span 被记录
# 3. 输入/输出被记录
```

**预期结果**：
- 在 Langfuse Dashboard 中看到一个 Trace
- Trace 中包含多个 Span（对应每个节点）
- 每个 Span 显示节点名称、输入、输出、耗时

### 测试 2：带 LLM 调用的简单 LangGraph

**目的**：
- 验证 LLM 调用被正确追踪
- 验证 Generation 类型的 Span
- 验证 tokens 使用情况

**测试内容**：
```python
# 创建一个包含 LLM 调用的简单 LangGraph
# 节点中调用 get_llm() 获取 LLM 并调用
# 使用 LangfuseCallbackHandler 追踪
# 验证：
# 1. LLM 调用被记录为 Generation Span
# 2. 输入消息、输出消息被记录
# 3. Tokens 使用情况被记录（如果支持）
```

**预期结果**：
- 在 Dashboard 中看到 Trace 和 Span
- LLM 调用显示为 Generation 类型的 Span
- 可以看到输入 prompt 和输出 response
- 可以看到 tokens 统计（如果 LLM 支持）

### 测试 3：使用项目中的路由图（简化版）

**目的**：
- 在项目实际代码中集成 Langfuse
- 验证复杂图的追踪
- 验证条件路由的追踪

**测试内容**：
```python
# 使用 domain/router/graph.py 中的 create_router_graph
# 创建路由图（可能需要 mock checkpointer）
# 调用路由图，传入简单的测试消息
# 使用 LangfuseCallbackHandler 追踪
# 验证：
# 1. 路由节点被追踪
# 2. 条件路由逻辑被追踪
# 3. 智能体节点被追踪（如果被调用）
```

**预期结果**：
- 在 Dashboard 中看到完整的路由图执行流程
- 可以看到路由决策过程
- 可以看到各个节点的输入/输出

### 测试 4：完整的路由图调用（模拟真实场景）

**目的**：
- 模拟真实的聊天请求
- 验证多轮对话的追踪
- 验证元数据（user_id, session_id）的传递

**测试内容**：
```python
# 模拟完整的聊天请求
# 包含多轮对话
# 设置 user_id、session_id 等元数据
# 使用 trace 的 metadata 功能
# 验证：
# 1. 多轮对话的 Trace 关联
# 2. 用户 ID、会话 ID 等元数据被记录
# 3. 完整的执行链路被追踪
```

**预期结果**：
- 在 Dashboard 中看到完整的对话流程
- 可以看到用户 ID、会话 ID 等元数据
- 可以看到多轮对话的关联关系

## 🔧 技术实现要点

### 1. 环境配置
- 从 `.env` 文件读取 Langfuse 凭据
- 使用 `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`LANGFUSE_BASE_URL`

### 2. 回调机制
- 使用 `LangfuseCallbackHandler` 作为 LangChain 回调
- 通过 `RunnableConfig` 传入回调
- 支持 `invoke()` 和 `astream()` 方法

### 3. Trace 管理
- 使用 `langfuse.trace()` 创建 Trace
- 通过 `trace.get_langchain_handler()` 获取回调处理器
- 设置 Trace 的元数据（user_id, session_id 等）

### 4. 节点追踪
- 每个 LangGraph 节点自动作为 Span 被追踪
- 可以使用 `@observe()` 装饰器自定义节点追踪
- 可以手动创建 Span 记录关键操作

## 📊 验证方法

### 在 Langfuse Dashboard 中验证

1. **访问 Dashboard**
   - 登录 https://us.cloud.langfuse.com
   - 进入 Traces 页面

2. **查看 Trace 列表**
   - 应该能看到测试创建的 Trace
   - Trace 名称应该清晰标识测试用例

3. **查看 Trace 详情**
   - 点击 Trace 查看详情
   - 应该能看到完整的执行链路
   - 每个节点应该显示为 Span

4. **查看 Span 详情**
   - 点击 Span 查看详情
   - 应该能看到输入/输出
   - LLM 调用应该显示 Generation 信息

5. **查看元数据**
   - 在 Trace 详情中查看 metadata
   - 应该能看到 user_id、session_id 等信息

## 🚀 执行步骤

1. **安装依赖**
   ```bash
   pip install langfuse
   ```

2. **运行测试 1**
   - 执行最简单的测试
   - 在 Dashboard 中验证结果

3. **运行测试 2**
   - 执行带 LLM 的测试
   - 在 Dashboard 中验证 LLM 调用追踪

4. **运行测试 3**
   - 执行路由图测试
   - 在 Dashboard 中验证复杂图的追踪

5. **运行测试 4**
   - 执行完整场景测试
   - 在 Dashboard 中验证元数据和多轮对话

## 📌 注意事项

1. **环境变量**
   - 确保 `.env` 文件中的 Langfuse 凭据正确
   - 确保 `LANGFUSE_BASE_URL` 指向正确的实例

2. **异步调用**
   - 项目使用异步，注意使用 `astream()` 而不是 `stream()`
   - 注意回调处理器的异步兼容性

3. **Checkpointer**
   - 测试 3-4 可能需要 mock checkpointer
   - 或者使用内存 checkpointer

4. **LLM 调用**
   - 测试 2-4 会调用真实 LLM，注意成本
   - 可以使用测试专用的模型或降低调用频率

5. **Trace 命名**
   - 为每个测试用例设置清晰的 Trace 名称
   - 便于在 Dashboard 中识别和对比

## 🎓 学习成果

完成所有测试后，应该能够：
1. ✅ 理解 Langfuse 的基本用法
2. ✅ 掌握在 LangGraph 中集成 Langfuse 的方法
3. ✅ 能够在 Dashboard 中查看和分析执行流程
4. ✅ 为生产环境集成做好准备

## 📚 参考资料

- [Langfuse 官方文档](https://langfuse.com/docs)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [LangChain 回调文档](https://python.langchain.com/docs/modules/callbacks/)

