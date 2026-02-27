# Langfuse 分布式追踪实现方案

## 问题场景

**场景描述**：
- **服务器A**：主流程服务器
  - 流程：开始节点 → 节点A → 节点B → 结束
  - 节点A会调用服务器B的接口
- **服务器B**：子流程服务器
  - 需要将自己的执行记录作为节点A的子节点（节点A-1）

**目标**：实现跨服务器的追踪关联，让服务器B的执行记录成为服务器A节点A的子节点。

## 解决方案

### 核心机制：使用 `trace_context` 参数

Langfuse 支持通过 `trace_context` 参数实现分布式追踪：

```python
trace_context = {
    "trace_id": "trace_id",      # 关联到同一个 Trace
    "parent_span_id": "span_id"  # 指定父 Span ID（可选）
}
```

### 实现步骤

#### 1. 服务器A：在调用服务器B前获取当前 Span 信息

```python
# 服务器A：节点A的执行
with client.start_as_current_span(name="节点A") as span_a:
    # 获取当前 span 的信息
    current_trace_id = client.get_current_trace_id()
    current_span_id = span_a.id  # 或者通过其他方式获取
    
    # 调用服务器B的接口，传递追踪信息
    response = await call_server_b(
        data=some_data,
        trace_id=current_trace_id,
        parent_span_id=current_span_id  # 关键：传递父 span ID
    )
```

#### 2. 服务器B：接收追踪信息并创建关联的 Span

```python
# 服务器B：接收请求
@app.post("/api/process")
async def process(request: Request):
    # 从请求头或请求体中获取追踪信息
    trace_id = request.headers.get("X-Trace-ID")
    parent_span_id = request.headers.get("X-Parent-Span-ID")
    
    # 使用 trace_context 创建关联的 Span
    trace_context = {
        "trace_id": trace_id,
        "parent_span_id": parent_span_id  # 指定父 Span
    }
    
    with client.start_as_current_span(
        name="节点A-1",
        trace_context=trace_context  # 关键：使用 trace_context
    ):
        # 执行服务器B的业务逻辑
        result = do_something()
        return result
```

## 完整实现示例

### 服务器A代码示例

```python
# 服务器A：app/api/routes.py 或类似文件

from langfuse import Langfuse
import httpx

# 初始化 Langfuse 客户端
langfuse_client = Langfuse(
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    host=settings.LANGFUSE_HOST
)

async def execute_node_a():
    """执行节点A，调用服务器B"""
    
    # 在 Trace 上下文中创建节点A
    with langfuse_client.start_as_current_span(
        name="节点A",
        input={"step": "A", "data": "some data"}
    ) as span_a:
        # 获取当前追踪信息
        current_trace_id = langfuse_client.get_current_trace_id()
        current_span_id = span_a.id  # 获取当前 span 的 ID
        
        print(f"节点A: trace_id={current_trace_id}, span_id={current_span_id}")
        
        # 调用服务器B的接口
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://server-b/api/process",
                json={
                    "data": "some data to process"
                },
                headers={
                    "X-Trace-ID": current_trace_id,           # 传递 trace_id
                    "X-Parent-Span-ID": current_span_id,      # 传递父 span ID
                    "Content-Type": "application/json"
                }
            )
        
        result = response.json()
        
        # 更新节点A的输出
        span_a.update(output=result)
        
        return result
```

### 服务器B代码示例

```python
# 服务器B：app/api/routes.py 或类似文件

from langfuse import Langfuse
from fastapi import FastAPI, Request, Header
from typing import Optional

app = FastAPI()

# 初始化 Langfuse 客户端
langfuse_client = Langfuse(
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    host=settings.LANGFUSE_HOST
)

@app.post("/api/process")
async def process(
    request: Request,
    data: dict,
    x_trace_id: Optional[str] = Header(None, alias="X-Trace-ID"),
    x_parent_span_id: Optional[str] = Header(None, alias="X-Parent-Span-ID")
):
    """
    处理请求，并关联到服务器A的追踪
    
    Args:
        request: FastAPI 请求对象
        data: 请求数据
        x_trace_id: 追踪 ID（从请求头获取）
        x_parent_span_id: 父 Span ID（从请求头获取）
    """
    
    if not x_trace_id:
        # 如果没有 trace_id，创建一个新的 trace
        trace_context = None
        logger.warning("未收到 trace_id，将创建新的 trace")
    else:
        # 构建 trace_context，关联到服务器A的追踪
        trace_context = {
            "trace_id": x_trace_id,
        }
        
        # 如果有 parent_span_id，指定父 Span
        if x_parent_span_id:
            trace_context["parent_span_id"] = x_parent_span_id
            logger.info(
                f"关联到父 Span: trace_id={x_trace_id}, "
                f"parent_span_id={x_parent_span_id}"
            )
        else:
            logger.info(f"关联到 Trace: trace_id={x_trace_id}")
    
    # 使用 trace_context 创建 Span（会自动关联到服务器A的 Trace）
    with langfuse_client.start_as_current_span(
        name="节点A-1",
        trace_context=trace_context,  # 关键：使用 trace_context
        input={"received_data": data},
        metadata={
            "server": "server-b",
            "endpoint": "/api/process"
        }
    ) as span_b:
        # 执行服务器B的业务逻辑
        logger.info("服务器B开始处理...")
        
        # 模拟处理过程
        processed_data = {
            "original": data,
            "processed": "处理后的数据",
            "timestamp": datetime.now().isoformat()
        }
        
        # 可以创建子 Span（如果需要）
        with langfuse_client.start_as_current_span(
            name="节点A-1-子任务",
            input={"sub_task": "some sub task"}
        ):
            # 子任务逻辑
            sub_result = do_sub_task()
            processed_data["sub_result"] = sub_result
        
        # 更新 Span 输出
        span_b.update(output=processed_data)
        
        logger.info("服务器B处理完成")
        
        return {
            "status": "success",
            "data": processed_data
        }
```

## 关键点说明

### 1. 传递追踪信息

**方式1：通过 HTTP 请求头传递（推荐）**
```python
headers = {
    "X-Trace-ID": trace_id,
    "X-Parent-Span-ID": parent_span_id
}
```

**方式2：通过请求体传递**
```python
body = {
    "data": {...},
    "trace_context": {
        "trace_id": trace_id,
        "parent_span_id": parent_span_id
    }
}
```

**方式3：通过查询参数传递（不推荐，安全性较低）**
```python
params = {
    "trace_id": trace_id,
    "parent_span_id": parent_span_id
}
```

### 2. 获取 Span ID

在服务器A中，需要获取当前 Span 的 ID：

```python
# 方式1：从上下文管理器返回值获取
with client.start_as_current_span(name="节点A") as span:
    span_id = span.id  # 获取 Span ID

# 方式2：通过 Langfuse SDK 的方法获取（如果支持）
span_id = client.get_current_span_id()  # 需要确认 SDK 是否支持
```

### 3. trace_context 参数说明

```python
trace_context = {
    "trace_id": "trace_id",        # 必需：关联到同一个 Trace
    "parent_span_id": "span_id"   # 可选：指定父 Span ID
}
```

- **如果只提供 `trace_id`**：服务器B的 Span 会关联到同一个 Trace，但不会成为节点A的子节点（会成为 Trace 的直接子节点）
- **如果同时提供 `trace_id` 和 `parent_span_id`**：服务器B的 Span 会成为指定 Span 的子节点

### 4. 层级结构

**理想情况**（同时传递 trace_id 和 parent_span_id）：
```
Trace
  └─ 节点A (服务器A)
      └─ 节点A-1 (服务器B)  ← 成为节点A的子节点
```

**如果只传递 trace_id**：
```
Trace
  ├─ 节点A (服务器A)
  └─ 节点A-1 (服务器B)  ← 与节点A同级
```

## 实际应用建议

### 1. 创建追踪信息传递工具函数

```python
# 服务器A：utils/tracing.py

from langfuse import Langfuse
from typing import Optional, Dict

def get_trace_context(client: Langfuse) -> Dict[str, Optional[str]]:
    """
    获取当前追踪上下文信息
    
    Returns:
        Dict包含 trace_id 和 span_id
    """
    trace_id = client.get_current_trace_id()
    # 注意：需要从当前 span 获取 span_id
    # 可能需要通过其他方式获取，如从上下文管理器返回值
    
    return {
        "trace_id": trace_id,
        "span_id": None  # 需要根据实际情况获取
    }

def build_trace_headers(client: Langfuse, span_id: Optional[str] = None) -> Dict[str, str]:
    """
    构建包含追踪信息的 HTTP 请求头
    
    Args:
        client: Langfuse 客户端
        span_id: 当前 Span ID（如果已知）
        
    Returns:
        包含追踪信息的请求头字典
    """
    trace_id = client.get_current_trace_id()
    headers = {
        "X-Trace-ID": trace_id or "",
    }
    
    if span_id:
        headers["X-Parent-Span-ID"] = span_id
    
    return headers
```

### 2. 在服务器B中创建中间件

```python
# 服务器B：middleware/tracing.py

from fastapi import Request
from langfuse import Langfuse
from typing import Optional

def extract_trace_context(request: Request) -> Optional[dict]:
    """
    从请求中提取追踪上下文
    
    Returns:
        trace_context 字典，如果未找到则返回 None
    """
    trace_id = request.headers.get("X-Trace-ID")
    parent_span_id = request.headers.get("X-Parent-Span-ID")
    
    if not trace_id:
        return None
    
    trace_context = {"trace_id": trace_id}
    if parent_span_id:
        trace_context["parent_span_id"] = parent_span_id
    
    return trace_context
```

### 3. 使用装饰器简化代码

```python
# 服务器B：decorators/tracing.py

from functools import wraps
from fastapi import Request
from langfuse import Langfuse

def with_trace_context(func):
    """
    装饰器：自动处理追踪上下文
    """
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        # 提取追踪上下文
        trace_context = extract_trace_context(request)
        
        # 如果有追踪上下文，创建关联的 Span
        if trace_context:
            with langfuse_client.start_as_current_span(
                name=func.__name__,
                trace_context=trace_context
            ):
                return await func(request, *args, **kwargs)
        else:
            # 没有追踪上下文，正常执行
            return await func(request, *args, **kwargs)
    
    return wrapper

# 使用示例
@app.post("/api/process")
@with_trace_context
async def process(request: Request, data: dict):
    # 函数内部会自动在追踪上下文中执行
    return {"status": "success"}
```

## 注意事项

### 1. Span ID 的获取

Langfuse SDK 可能不直接提供获取当前 Span ID 的方法，可能需要：
- 从上下文管理器返回值获取：`with client.start_as_current_span(...) as span: span.id`
- 或者使用 OpenTelemetry 的 API 获取

### 2. trace_id 格式

确保 trace_id 符合 Langfuse 的要求（32 个小写十六进制字符）：
```python
def normalize_trace_id(trace_id: str) -> str:
    """规范化 trace_id"""
    return trace_id.replace("-", "").lower()
```

### 3. 错误处理

如果服务器B无法获取追踪信息，应该：
- 记录警告日志
- 创建新的 Trace（而不是失败）
- 或者返回错误（根据业务需求）

### 4. 性能考虑

- 追踪信息的传递不应该影响业务逻辑
- 如果追踪服务不可用，应该优雅降级

## 总结

**答案：可以！** 服务器B可以将自己的执行记录作为服务器A节点A的子节点。

**实现方式**：
1. ✅ 服务器A在调用服务器B时，传递 `trace_id` 和 `parent_span_id`
2. ✅ 服务器B接收这些信息，使用 `trace_context` 参数创建 Span
3. ✅ Langfuse 会自动关联到同一个 Trace，并建立父子关系

**关键代码**：
```python
# 服务器A：传递追踪信息
headers = {
    "X-Trace-ID": trace_id,
    "X-Parent-Span-ID": span_id
}

# 服务器B：使用 trace_context 创建关联的 Span
with client.start_as_current_span(
    name="节点A-1",
    trace_context={
        "trace_id": trace_id,
        "parent_span_id": parent_span_id
    }
):
    # 执行逻辑
    pass
```

