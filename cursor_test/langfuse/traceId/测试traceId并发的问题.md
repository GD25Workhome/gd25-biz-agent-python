# 测试traceId并发的问题

## 一、测试目标

验证在使用全局 Langfuse 客户端（单例模式）的情况下，多个并发线程/协程同时调用 `set_langfuse_trace_context()` 时，是否会出现 traceId 串用的问题。

## 二、问题背景

### 2.1 潜在问题

在 `01_Agent/backend/infrastructure/observability/langfuse_handler.py` 中：

1. **全局客户端单例**：`_langfuse_client` 是全局变量，所有请求共享同一个客户端实例
2. **ContextVar 隔离**：使用 `ContextVar` 在异步上下文中传递 trace_id
3. **可能的串用风险**：如果 Langfuse SDK 的 `trace()` 或 `update_current_trace()` 方法内部使用了全局状态或线程本地存储，可能导致并发请求之间的 trace_id 串用

### 2.2 测试重点

- ✅ 验证 `ContextVar` 在并发场景下的隔离性
- ✅ 验证 Langfuse SDK 的 `trace()` 方法是否线程安全
- ✅ 验证多个并发请求的 trace_id 是否正确隔离
- ✅ 验证 Langfuse 服务端记录的 trace 信息是否正确

## 三、测试方案设计

### 3.1 测试原理

```
并发测试场景：
┌─────────────────────────────────────────────────────────┐
│  全局 Langfuse 客户端（单例）                            │
│  _langfuse_client                                       │
└─────────────────────────────────────────────────────────┘
           │
           ├─────────────────┬─────────────────┬─────────────┐
           │                 │                 │             │
    ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐     │
    │ 线程/协程 1  │   │ 线程/协程 2  │   │ 线程/协程 N  │     │
    │ trace_id:   │   │ trace_id:   │   │ trace_id:   │     │
    │ "trace_001" │   │ "trace_002" │   │ "trace_N"   │     │
    └─────────────┘   └─────────────┘   └─────────────┘     │
           │                 │                 │             │
           └─────────────────┴─────────────────┴─────────────┘
           │
    ┌──────▼──────────────────────────────────────────────┐
    │  验证：每个线程的 trace_id 是否正确隔离              │
    │  - ContextVar 中的值是否正确                        │
    │  - Langfuse 记录的 trace 信息是否正确               │
    └─────────────────────────────────────────────────────┘
```

### 3.2 测试场景

#### 场景1：多线程并发测试（同步场景）
- 使用 `threading.Thread` 创建多个线程
- 每个线程使用不同的 trace_id 调用 `set_langfuse_trace_context()`
- 验证每个线程的 ContextVar 值是否正确

#### 场景2：多协程并发测试（异步场景）
- 使用 `asyncio.gather()` 创建多个并发协程
- 每个协程使用不同的 trace_id 调用 `set_langfuse_trace_context()`
- 验证每个协程的 ContextVar 值是否正确

#### 场景3：混合并发测试（线程+协程）
- 同时使用线程和协程
- 验证在不同并发模型下的隔离性

#### 场景4：Langfuse 服务端验证
- 在并发测试后，查询 Langfuse 服务端
- 验证记录的 trace 信息是否正确，没有串用

### 3.3 测试数据设计

```python
测试数据：
- 并发数量：10, 50, 100（逐步增加）
- 每个请求的 trace_id：唯一标识（如 "trace_001", "trace_002", ...）
- 每个请求的 user_id：唯一标识（如 "user_001", "user_002", ...）
- 每个请求的 session_id：唯一标识（如 "session_001", "session_002", ...）
- 元数据：包含线程/协程标识，便于后续验证
```

## 四、测试步骤

### 4.1 准备阶段

1. **环境准备**
   - 确保 Langfuse 服务可用（或使用 Mock）
   - 配置 Langfuse 连接信息
   - 准备测试数据

2. **测试工具准备**
   - 创建测试辅助函数
   - 准备结果收集机制

### 4.2 执行阶段

#### 步骤1：多线程并发测试

```python
# 伪代码示例
def test_multithread_trace_id_isolation():
    results = {}
    
    def worker(thread_id, trace_id):
        # 调用 set_langfuse_trace_context
        actual_trace_id = set_langfuse_trace_context(
            name=f"test_trace_{thread_id}",
            user_id=f"user_{thread_id}",
            session_id=f"session_{thread_id}",
            trace_id=trace_id,
            metadata={"thread_id": thread_id}
        )
        
        # 获取 ContextVar 中的值
        context_trace_id = get_current_trace_id()
        
        # 记录结果
        results[thread_id] = {
            "expected": trace_id,
            "actual": actual_trace_id,
            "context": context_trace_id,
            "match": actual_trace_id == trace_id and context_trace_id == trace_id
        }
    
    # 创建多个线程并发执行
    threads = []
    for i in range(100):
        trace_id = f"trace_{i:03d}"
        t = threading.Thread(target=worker, args=(i, trace_id))
        threads.append(t)
        t.start()
    
    # 等待所有线程完成
    for t in threads:
        t.join()
    
    # 验证结果
    assert all(r["match"] for r in results.values())
```

#### 步骤2：多协程并发测试

```python
# 伪代码示例
async def test_async_trace_id_isolation():
    results = {}
    
    async def worker(coroutine_id, trace_id):
        # 调用 set_langfuse_trace_context
        actual_trace_id = set_langfuse_trace_context(
            name=f"test_trace_{coroutine_id}",
            user_id=f"user_{coroutine_id}",
            session_id=f"session_{coroutine_id}",
            trace_id=trace_id,
            metadata={"coroutine_id": coroutine_id}
        )
        
        # 获取 ContextVar 中的值
        context_trace_id = get_current_trace_id()
        
        # 记录结果
        results[coroutine_id] = {
            "expected": trace_id,
            "actual": actual_trace_id,
            "context": context_trace_id,
            "match": actual_trace_id == trace_id and context_trace_id == trace_id
        }
    
    # 创建多个协程并发执行
    tasks = []
    for i in range(100):
        trace_id = f"trace_{i:03d}"
        tasks.append(worker(i, trace_id))
    
    # 并发执行所有协程
    await asyncio.gather(*tasks)
    
    # 验证结果
    assert all(r["match"] for r in results.values())
```

#### 步骤3：Langfuse 服务端验证

```python
# 伪代码示例
def verify_langfuse_traces():
    """
    从 Langfuse 服务端查询 trace 信息，验证是否正确
    """
    langfuse_client = get_langfuse_client()
    
    # 查询最近创建的 trace
    # 注意：需要根据 Langfuse SDK 的实际 API 调整
    traces = langfuse_client.fetch_traces(limit=100)
    
    # 验证每个 trace 的信息是否正确
    for trace in traces:
        trace_id = trace.id
        user_id = trace.user_id
        session_id = trace.session_id
        metadata = trace.metadata
        
        # 验证 trace_id 与 user_id、session_id 的对应关系
        expected_user_id = f"user_{trace_id.split('_')[1]}"
        assert user_id == expected_user_id, f"Trace {trace_id} 的 user_id 不匹配"
```

### 4.3 验证阶段

1. **ContextVar 隔离验证**
   - 检查每个线程/协程的 ContextVar 值是否与预期一致
   - 验证不同线程/协程之间的值是否互相影响

2. **返回值验证**
   - 检查 `set_langfuse_trace_context()` 的返回值是否正确
   - 验证返回的 trace_id 是否与传入的 trace_id 一致

3. **Langfuse 服务端验证**
   - 查询 Langfuse 服务端，验证记录的 trace 信息
   - 检查是否有 trace_id 串用的情况

4. **统计信息**
   - 统计测试总数、成功数、失败数
   - 记录失败的具体情况（哪个 trace_id 串用了）

## 五、测试代码结构

```
cursor_test/langfuse/traceId/
├── 测试traceId并发的问题.md          # 本文档
├── test_trace_id_concurrency.py     # 测试实现代码
├── conftest.py                       # pytest 配置（可选）
└── README.md                         # 测试说明（可选）
```

### 5.1 测试代码模块设计

```python
# test_trace_id_concurrency.py 结构

class TestTraceIdConcurrency:
    """TraceId 并发测试类"""
    
    def setup_method(self):
        """测试前置准备"""
        pass
    
    def test_multithread_isolation(self):
        """测试多线程隔离"""
        pass
    
    def test_async_isolation(self):
        """测试异步协程隔离"""
        pass
    
    def test_mixed_concurrency(self):
        """测试混合并发（线程+协程）"""
        pass
    
    def test_langfuse_server_verification(self):
        """验证 Langfuse 服务端记录"""
        pass
```

## 六、预期结果

### 6.1 成功场景

- ✅ 所有线程/协程的 ContextVar 值正确，与预期 trace_id 一致
- ✅ `set_langfuse_trace_context()` 返回值正确
- ✅ Langfuse 服务端记录的 trace 信息正确，没有串用
- ✅ 不同并发模型下都能正确隔离

### 6.2 失败场景（如果存在问题）

- ❌ 某些线程/协程的 ContextVar 值被其他线程/协程覆盖
- ❌ `set_langfuse_trace_context()` 返回值与预期不一致
- ❌ Langfuse 服务端记录的 trace 信息出现串用
- ❌ 不同并发模型下出现不同的行为

### 6.3 问题定位

如果测试失败，需要进一步分析：

1. **问题类型**
   - ContextVar 隔离失效？
   - Langfuse SDK 内部状态共享？
   - 其他原因？

2. **问题范围**
   - 只在多线程场景出现？
   - 只在异步场景出现？
   - 所有场景都出现？

3. **问题频率**
   - 每次都能复现？
   - 偶尔出现？
   - 特定条件下出现？

## 七、测试执行

### 7.1 执行命令

```bash
# 运行所有测试
pytest cursor_test/langfuse/traceId/test_trace_id_concurrency.py -v

# 运行特定测试
pytest cursor_test/langfuse/traceId/test_trace_id_concurrency.py::TestTraceIdConcurrency::test_multithread_isolation -v

# 生成详细报告
pytest cursor_test/langfuse/traceId/test_trace_id_concurrency.py -v --html=report.html
```

### 7.2 测试环境要求

- Python 3.10+
- Langfuse SDK 已安装
- Langfuse 服务可用（或使用 Mock）
- pytest 测试框架

### 7.3 注意事项

1. **Langfuse 服务依赖**
   - 如果 Langfuse 服务不可用，可以使用 Mock 对象
   - 或者使用测试专用的 Langfuse 实例

2. **测试数据清理**
   - 测试后可能需要清理 Langfuse 中的测试数据
   - 或者使用独立的测试项目/环境

3. **并发数量**
   - 根据实际情况调整并发数量
   - 避免过多并发导致测试环境压力过大

## 八、后续行动

### 8.1 如果测试通过

- ✅ 确认当前实现是线程安全的
- ✅ 可以继续使用当前的实现方案
- ✅ 记录测试结果作为文档

### 8.2 如果测试失败

- ❌ 分析失败原因
- ❌ 定位问题所在（ContextVar、Langfuse SDK、或其他）
- ❌ 设计修复方案
- ❌ 重新测试验证修复效果

## 九、参考资料

- [Python ContextVar 文档](https://docs.python.org/3/library/contextvars.html)
- [Langfuse Python SDK 文档](https://langfuse.com/docs/sdk/python)
- [Pytest 并发测试最佳实践](https://docs.pytest.org/en/stable/)

