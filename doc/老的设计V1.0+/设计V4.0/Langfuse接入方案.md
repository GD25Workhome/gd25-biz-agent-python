# Langfuse 接入方案

## 1. 概述

### 1.1 需求背景

当前系统已有基础的 LLM 调用日志功能（V2.2 设计），但存在以下局限性：
- 日志存储在本地数据库，缺乏可视化和分析能力
- 无法进行成本分析、性能监控和提示词优化
- 缺乏统一的链路追踪和调试工具
- 难以进行 A/B 测试和提示词版本管理

Langfuse 是一个开源的 LLM 可观测性平台，提供：
- **实时监控**：LLM 调用追踪、延迟、成本分析
- **提示词管理**：版本控制、A/B 测试、提示词优化
- **链路追踪**：完整的请求链路可视化
- **成本分析**：Token 使用统计、成本计算
- **调试工具**：交互式调试界面，快速定位问题

### 1.2 接入目标

1. **最小侵入**：在现有 LLM 调用封装层集成，不影响业务逻辑
2. **渐进式接入**：支持与现有日志系统并存，可逐步迁移
3. **完整追踪**：追踪所有 LLM 调用（路由、Agent、工具调用）
4. **上下文关联**：关联 session_id、user_id、agent_key 等业务上下文
5. **LangGraph 支持**：支持 LangGraph 的完整链路追踪

### 1.3 技术选型

- **Langfuse SDK**：Python SDK，支持 LangChain 和 LangGraph
- **部署方式**：支持自托管（推荐）或云服务
- **集成方式**：通过 LangChain Callback Handler 集成

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI 应用层                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              API 路由 (app/api/routes.py)            │   │
│  └──────────────────┬───────────────────────────────────┘   │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   LangGraph 路由层                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │        路由图 (domain/router/graph.py)                │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │   │
│  │  │ 路由节点     │  │ Agent节点    │  │ 工具调用    │ │   │
│  │  └──────────────┘  └──────────────┘  └─────────────┘ │   │
│  └──────────────────┬───────────────────────────────────┘   │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    LLM 调用层                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      LLM 客户端 (infrastructure/llm/client.py)        │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │  LangChain ChatOpenAI                           │  │   │
│  │  │  ┌──────────────┐  ┌─────────────────────────┐ │  │   │
│  │  │  │ Langfuse     │  │ 现有日志回调            │ │  │   │
│  │  │  │ Callback     │  │ (LlmLogCallbackHandler) │ │  │   │
│  │  │  └──────────────┘  └─────────────────────────┘ │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────┬───────────────────────────────────┘   │
└─────────────────────┼───────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
┌──────────────────┐      ┌──────────────────┐
│   Langfuse 服务   │      │   本地数据库日志   │
│  (可观测性平台)    │      │  (现有日志系统)    │
└──────────────────┘      └──────────────────┘
```

### 2.2 集成点设计

#### 2.2.1 LLM 调用层集成

在 `infrastructure/llm/client.py` 的 `get_llm()` 函数中集成 Langfuse Callback：

```python
from langfuse.callback import CallbackHandler as LangfuseCallbackHandler

def get_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    log_context: Optional[LlmLogContext] = None,
    enable_logging: Optional[bool] = None,
    enable_langfuse: Optional[bool] = None,  # 新增参数
    **kwargs
) -> BaseChatModel:
    # ... 现有代码 ...
    
    callbacks: List[Any] = list(kwargs.pop("callbacks", []) or [])
    
    # 添加 Langfuse Callback（如果启用）
    if enable_langfuse is None:
        enable_langfuse = settings.LANGFUSE_ENABLED
    
    if enable_langfuse:
        langfuse_handler = create_langfuse_handler(log_context)
        callbacks.append(langfuse_handler)
    
    # 保留现有的日志回调
    callbacks.append(
        LlmLogCallbackHandler(...)
    )
    
    # ... 其余代码 ...
```

#### 2.2.2 LangGraph 集成

Langfuse 支持 LangGraph 的完整追踪，需要在图编译时传入 callback：

```python
from langfuse.decorators import langfuse_context

def create_router_graph(...):
    # ... 创建图 ...
    
    # 编译图时传入 Langfuse callback（如果启用）
    graph_config = {}
    if checkpointer:
        graph_config["checkpointer"] = checkpointer
    if store:
        graph_config["store"] = store
    
    # 如果启用 Langfuse，添加 callback
    if settings.LANGFUSE_ENABLED:
        langfuse_handler = create_langfuse_handler()
        graph_config["callbacks"] = [langfuse_handler]
    
    return workflow.compile(**graph_config)
```

#### 2.2.3 上下文传递

在 API 路由层设置 Langfuse 的 trace 上下文：

```python
from langfuse.decorators import langfuse_context

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, app_request: Request) -> ChatResponse:
    # 设置 Langfuse trace 上下文
    if settings.LANGFUSE_ENABLED:
        langfuse_context.update_current_trace(
            name="chat_request",
            user_id=request.user_id,
            session_id=request.session_id,
            metadata={
                "message_length": len(request.message),
                "history_count": len(request.conversation_history) if request.conversation_history else 0,
            }
        )
    
    # ... 执行路由图 ...
```

### 2.3 配置管理

在 `app/core/config.py` 中添加 Langfuse 配置：

```python
class Settings(BaseSettings):
    # ... 现有配置 ...
    
    # Langfuse 配置
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"  # 或自托管地址
    LANGFUSE_SESSION_ID: Optional[str] = None  # 可选，用于标识会话
```

## 3. 实现方案

### 3.1 依赖安装

在 `requirements.txt` 中添加：

```txt
# LLM 可观测性
langfuse>=2.0.0,<3.0.0
```

### 3.2 创建 Langfuse 集成模块

创建 `infrastructure/observability/langfuse_handler.py`：

```python
"""
Langfuse 集成模块
"""
from typing import Optional
from langfuse.callback import CallbackHandler as LangfuseCallbackHandler
from langfuse.decorators import langfuse_context

from app.core.config import settings
from infrastructure.observability.llm_logger import LlmLogContext


def create_langfuse_handler(
    context: Optional[LlmLogContext] = None
) -> LangfuseCallbackHandler:
    """
    创建 Langfuse Callback Handler
    
    Args:
        context: LLM 调用上下文
        
    Returns:
        LangfuseCallbackHandler: Langfuse 回调处理器
    """
    if not settings.LANGFUSE_ENABLED:
        raise ValueError("Langfuse 未启用，请设置 LANGFUSE_ENABLED=True")
    
    # 构建用户标识（优先使用 user_id，否则使用 session_id）
    user_id = None
    if context:
        user_id = context.user_id or context.session_id
    
    # 构建会话标识
    session_id = None
    if context:
        session_id = context.session_id or context.conversation_id
    
    # 构建元数据
    metadata = {}
    if context:
        if context.trace_id:
            metadata["trace_id"] = context.trace_id
        if context.agent_key:
            metadata["agent_key"] = context.agent_key
        if context.session_id:
            metadata["session_id"] = context.session_id
        if context.user_id:
            metadata["user_id"] = context.user_id
    
    handler = LangfuseCallbackHandler(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_HOST,
        session_id=session_id,
        user_id=user_id,
        metadata=metadata if metadata else None,
    )
    
    return handler


def set_langfuse_trace_context(
    name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    设置 Langfuse trace 上下文
    
    Args:
        name: trace 名称
        user_id: 用户 ID
        session_id: 会话 ID
        metadata: 元数据
    """
    if not settings.LANGFUSE_ENABLED:
        return
    
    langfuse_context.update_current_trace(
        name=name,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata,
    )
```

### 3.3 修改 LLM 客户端

修改 `infrastructure/llm/client.py`：

```python
from infrastructure.observability.langfuse_handler import create_langfuse_handler

def get_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    log_context: Optional[LlmLogContext] = None,
    enable_logging: Optional[bool] = None,
    enable_langfuse: Optional[bool] = None,  # 新增参数
    **kwargs
) -> BaseChatModel:
    # ... 现有代码 ...
    
    callbacks: List[Any] = list(kwargs.pop("callbacks", []) or [])
    
    # 添加 Langfuse Callback（如果启用）
    enable_langfuse_flag = enable_langfuse if enable_langfuse is not None else settings.LANGFUSE_ENABLED
    if enable_langfuse_flag:
        try:
            langfuse_handler = create_langfuse_handler(log_context)
            callbacks.append(langfuse_handler)
        except Exception as e:
            logger.warning(f"创建 Langfuse handler 失败: {e}，继续执行但不记录到 Langfuse")
    
    # 保留现有的日志回调
    callbacks.append(
        LlmLogCallbackHandler(...)
    )
    
    # ... 其余代码保持不变 ...
```

### 3.4 修改路由图创建

修改 `domain/router/graph.py`：

```python
from infrastructure.observability.langfuse_handler import create_langfuse_handler

def create_router_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    pool: Optional[AsyncConnectionPool] = None,
    store: Optional[BaseStore] = None,
):
    # ... 创建图的代码 ...
    
    # 编译图
    graph_config = {}
    if checkpointer:
        graph_config["checkpointer"] = checkpointer
    if store:
        graph_config["store"] = store
    
    # 如果启用 Langfuse，添加全局 callback
    if settings.LANGFUSE_ENABLED:
        try:
            langfuse_handler = create_langfuse_handler()
            # LangGraph 支持在编译时传入 callbacks
            # 注意：这会影响所有节点的执行
            if "callbacks" not in graph_config:
                graph_config["callbacks"] = []
            graph_config["callbacks"].append(langfuse_handler)
        except Exception as e:
            logger.warning(f"为路由图添加 Langfuse callback 失败: {e}")
    
    return workflow.compile(**graph_config)
```

### 3.5 修改 API 路由

修改 `app/api/routes.py`：

```python
from infrastructure.observability.langfuse_handler import set_langfuse_trace_context

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    app_request: Request
) -> ChatResponse:
    # 设置 Langfuse trace 上下文
    if settings.LANGFUSE_ENABLED:
        set_langfuse_trace_context(
            name="chat_request",
            user_id=request.user_id,
            session_id=request.session_id,
            metadata={
                "message_length": len(request.message),
                "history_count": len(request.conversation_history) if request.conversation_history else 0,
            }
        )
    
    # ... 其余代码保持不变 ...
```

### 3.6 环境变量配置

在 `.env.example` 中添加：

```env
# Langfuse 配置
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_HOST=https://cloud.langfuse.com
```

## 4. 部署方案

### 4.1 Langfuse 服务部署

#### 方案一：使用 Langfuse Cloud（推荐用于开发/测试）

1. 注册账号：https://cloud.langfuse.com
2. 创建项目，获取 Public Key 和 Secret Key
3. 配置环境变量即可

#### 方案二：自托管部署（推荐用于生产环境）

使用 Docker Compose 部署：

```yaml
# docker-compose.langfuse.yml
version: '3.8'

services:
  langfuse:
    image: langfuse/langfuse:latest
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://langfuse:langfuse@postgres:5432/langfuse
      - NEXTAUTH_SECRET=your-secret-key
      - NEXTAUTH_URL=http://localhost:3000
      - SALT=your-salt
    depends_on:
      - postgres
    restart: unless-stopped

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=langfuse
      - POSTGRES_PASSWORD=langfuse
      - POSTGRES_DB=langfuse
    volumes:
      - langfuse_db:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  langfuse_db:
```

启动服务：

```bash
docker-compose -f docker-compose.langfuse.yml up -d
```

访问：http://localhost:3000

### 4.2 应用配置

在 `.env` 中配置：

```env
# 使用自托管 Langfuse
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=http://localhost:3000
```

## 5. 功能特性

### 5.1 链路追踪

- **Trace 级别**：每个 API 请求创建一个 trace
- **Span 级别**：每个 LLM 调用创建一个 span
- **关联关系**：通过 session_id、user_id 关联业务上下文

### 5.2 成本分析

- **Token 统计**：自动统计 prompt_tokens、completion_tokens
- **成本计算**：根据模型和 Token 使用量计算成本
- **趋势分析**：查看成本趋势和异常

### 5.3 性能监控

- **延迟监控**：LLM 调用延迟统计
- **错误追踪**：失败调用的错误信息
- **吞吐量**：请求量和成功率

### 5.4 提示词管理

- **版本控制**：提示词版本管理
- **A/B 测试**：对比不同提示词的效果
- **优化建议**：基于数据提供优化建议

### 5.5 调试工具

- **交互式调试**：查看完整的请求/响应
- **链路可视化**：图形化展示调用链路
- **上下文查看**：查看完整的对话上下文

## 6. 迁移策略

### 6.1 渐进式接入

1. **阶段一**：并行运行（Langfuse + 现有日志系统）
   - 同时记录到 Langfuse 和本地数据库
   - 验证 Langfuse 数据的准确性

2. **阶段二**：逐步切换
   - 将主要监控切换到 Langfuse
   - 保留本地日志作为备份

3. **阶段三**：完全迁移（可选）
   - 如果 Langfuse 满足所有需求，可以停用本地日志
   - 或保留本地日志用于审计

### 6.2 数据一致性

- **双重记录**：初期同时记录到两个系统，确保数据一致性
- **数据对比**：定期对比两个系统的数据，验证准确性
- **回退机制**：如果 Langfuse 出现问题，可以快速回退到本地日志

## 7. 注意事项

### 7.1 性能影响

- Langfuse SDK 是异步的，对性能影响很小
- 如果 Langfuse 服务不可用，SDK 会降级处理，不影响主流程

### 7.2 数据隐私

- **敏感数据**：确保 Langfuse 服务符合数据隐私要求
- **数据脱敏**：可以对敏感字段进行脱敏处理
- **访问控制**：配置 Langfuse 的访问权限

### 7.3 网络依赖

- **离线模式**：Langfuse SDK 支持离线模式（数据本地缓存，稍后上传）
- **重试机制**：自动重试失败的请求
- **降级处理**：如果 Langfuse 不可用，不影响主流程

### 7.4 成本考虑

- **自托管**：需要额外的服务器资源
- **云服务**：按使用量付费
- **数据存储**：长期存储会产生存储成本

## 8. 测试方案

### 8.1 单元测试

测试 Langfuse handler 的创建和配置：

```python
def test_create_langfuse_handler():
    context = LlmLogContext(
        user_id="user_123",
        session_id="session_456",
        agent_key="test_agent"
    )
    handler = create_langfuse_handler(context)
    assert handler is not None
```

### 8.2 集成测试

测试完整的调用链路：

```python
async def test_langfuse_integration():
    # 配置 Langfuse
    settings.LANGFUSE_ENABLED = True
    settings.LANGFUSE_PUBLIC_KEY = "test_key"
    settings.LANGFUSE_SECRET_KEY = "test_secret"
    
    # 执行 LLM 调用
    llm = get_llm(enable_langfuse=True)
    result = await llm.ainvoke("Hello")
    
    # 验证 Langfuse 记录（需要访问 Langfuse API 或 Mock）
    # ...
```

### 8.3 端到端测试

测试完整的 API 请求链路：

```python
async def test_chat_with_langfuse():
    response = await client.post("/api/v1/chat", json={
        "message": "测试消息",
        "session_id": "test_session",
        "user_id": "test_user"
    })
    assert response.status_code == 200
    
    # 验证 Langfuse 中有对应的 trace
    # ...
```

## 9. 监控与告警

### 9.1 健康检查

定期检查 Langfuse 服务的可用性：

```python
async def check_langfuse_health():
    try:
        # 检查 Langfuse 服务是否可用
        # ...
        return True
    except Exception:
        return False
```

### 9.2 告警配置

- **服务不可用**：Langfuse 服务长时间不可用
- **数据丢失**：检测到数据未正确记录
- **性能异常**：Langfuse 调用延迟过高

## 10. 实施计划

### 10.1 第一阶段：基础集成（1-2天）

- [ ] 安装 Langfuse SDK
- [ ] 创建 Langfuse handler 模块
- [ ] 修改 LLM 客户端集成 Langfuse callback
- [ ] 配置环境变量
- [ ] 基础功能测试

### 10.2 第二阶段：完整集成（2-3天）

- [ ] 集成 LangGraph 追踪
- [ ] 添加 API 路由层的 trace 上下文
- [ ] 完善元数据和上下文传递
- [ ] 集成测试

### 10.3 第三阶段：部署与优化（1-2天）

- [ ] 部署 Langfuse 服务（自托管或云服务）
- [ ] 配置访问权限和安全设置
- [ ] 性能优化和监控
- [ ] 文档更新

### 10.4 第四阶段：验证与迁移（持续）

- [ ] 并行运行验证数据一致性
- [ ] 逐步切换到 Langfuse 作为主要监控工具
- [ ] 用户培训和文档

## 11. 总结

### 11.1 优势

- **最小侵入**：通过 Callback 机制集成，不影响现有代码
- **功能强大**：提供完整的可观测性能力
- **易于使用**：Web UI 界面友好，易于调试和分析
- **开源免费**：支持自托管，无供应商锁定

### 11.2 风险与应对

- **服务依赖**：Langfuse 服务不可用时，SDK 会降级处理，不影响主流程
- **数据隐私**：使用自托管部署，确保数据安全
- **性能影响**：SDK 是异步的，性能影响可忽略

### 11.3 后续优化

- **提示词管理**：利用 Langfuse 的提示词版本管理功能
- **A/B 测试**：使用 Langfuse 进行提示词效果对比
- **成本优化**：基于 Langfuse 的成本分析优化模型使用
