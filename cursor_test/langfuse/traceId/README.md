# TraceId 并发测试

## 简介

此测试用于验证在多线程和多协程并发场景下，Langfuse traceId 是否会出现串用问题。

## 测试内容

1. **多线程并发测试**：使用 `threading.Thread` 创建多个线程，每个线程使用不同的 traceId
2. **多协程并发测试**：使用 `asyncio.gather()` 创建多个并发协程，每个协程使用不同的 traceId
3. **混合并发测试**：同时使用线程和协程，验证在不同并发模型下的隔离性

## 运行方式

### 方式1：直接运行

```bash
# 在项目根目录执行
python cursor_test/langfuse/traceId/test_trace_id_concurrency.py
```

### 方式2：作为模块运行

```bash
# 在项目根目录执行
python -m cursor_test.langfuse.traceId.test_trace_id_concurrency
```

## 测试输出

测试会输出以下信息：

1. **每个测试的执行结果**：
   - ✅ 通过：所有 traceId 都正确隔离
   - ❌ 失败：发现 traceId 串用或值不匹配

2. **详细统计**：
   - 执行时间
   - 成功/失败数量
   - traceId 串用情况（如果有）

3. **测试总结**：
   - 总通过数
   - 总失败数
   - 成功率

## 测试结果解读

### 成功场景

```
✅ 多线程并发测试 (并发数: 50): 所有 50 个线程的 traceId 都正确隔离
✅ 多协程并发测试 (并发数: 50): 所有 50 个协程的 traceId 都正确隔离
✅ 混合并发测试 (线程: 25, 协程: 25): 所有 50 个任务的 traceId 都正确隔离
```

### 失败场景（如果存在问题）

```
❌ 多线程并发测试 (并发数: 50): 成功 45/50, actual串用: 2, context串用: 1
  详情: {
    "actual_collisions": {
      "trace_001": [1, 5, 12],  # trace_001 被线程 1, 5, 12 使用
      "trace_002": [3, 8]        # trace_002 被线程 3, 8 使用
    }
  }
```

## 注意事项

1. **Langfuse 服务依赖**：
   - 如果 Langfuse 服务不可用，测试仍会运行，但只验证 ContextVar 隔离性
   - 要启用完整测试，请配置 Langfuse 连接信息（`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` 等）

2. **测试环境**：
   - 建议在独立的测试环境中运行
   - 测试会在 Langfuse 中创建测试数据（如果 Langfuse 可用）

3. **并发数量**：
   - 默认并发数为 50，可以根据实际情况调整
   - 如果测试环境性能较低，可以减少并发数

## 测试原理

测试通过以下方式验证 traceId 隔离性：

1. **ContextVar 验证**：检查每个线程/协程的 `get_current_trace_id()` 返回值是否正确
2. **返回值验证**：检查 `set_langfuse_trace_context()` 的返回值是否正确
3. **串用检测**：统计是否有多个线程/协程使用了相同的 traceId

## 文件说明

- **`test_trace_id_concurrency.py`**: 主测试文件
- **`langfuse_handler.py`**: Langfuse Handler 的本地副本（用于测试，不依赖项目配置）
- **`测试traceId并发的问题.md`**: 测试方案文档

### 关于本地副本

测试使用 `langfuse_handler.py` 的本地副本，而不是直接导入项目中的模块。这样做的好处：

1. **独立性**：测试不依赖项目的配置系统
2. **可修改性**：可以针对测试需求修改代码
3. **配置读取**：从项目根目录的 `.env` 文件读取 Langfuse 配置

本地副本与原始文件的区别：
- 不依赖 `backend.app.config.settings`
- 使用 `TestSettings` 类从项目根目录的 `.env` 文件读取配置
- 支持使用 `python-dotenv` 库（如果已安装），否则使用手动解析
- 其他逻辑保持一致

### 配置读取方式

测试会从项目根目录的 `.env` 文件中读取以下配置：

- `LANGFUSE_ENABLED`: 是否启用 Langfuse（默认 false）
- `LANGFUSE_PUBLIC_KEY`: Langfuse 公钥
- `LANGFUSE_SECRET_KEY`: Langfuse 密钥
- `LANGFUSE_HOST`: Langfuse 服务器地址（可选）

如果 `.env` 文件中没有这些配置，会回退到环境变量。如果都没有，则使用默认值。

## 相关文档

- [测试方案文档](./测试traceId并发的问题.md)
- [原始 Langfuse Handler 实现](../../../01_Agent/backend/infrastructure/observability/langfuse_handler.py)

