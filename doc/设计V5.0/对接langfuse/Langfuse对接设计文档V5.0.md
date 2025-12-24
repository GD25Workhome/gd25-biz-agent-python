# Langfuse 对接设计文档 V5.0

## 文档信息

- **版本**: V5.0
- **创建日期**: 2025-01-XX
- **作者**: 系统架构组
- **状态**: 设计阶段

---

## 目录

1. [概述](#1-概述)
2. [Langfuse 能力分析](#2-langfuse-能力分析)
3. [当前系统现状分析](#3-当前系统现状分析)
4. [对接能力评估](#4-对接能力评估)
5. [代码结构调整分析](#5-代码结构调整分析)
6. [最终方案设计](#6-最终方案设计)
7. [实施步骤](#7-实施步骤)
8. [待办事项清单](#8-待办事项清单)

---

## 1. 概述

### 1.1 背景

当前系统已经集成了 Langfuse 的**提示词模版管理**功能，但尚未集成 Langfuse 的**可观测性**功能（Traces、Spans、Generations）。本文档旨在分析：

1. **当前代码可以对接 Langfuse 的哪些能力**
2. **对接前是否需要做结构调整，以达到更好的效果**

### 1.2 目标

- 全面对接 Langfuse 的可观测性能力
- 实现完整的链路追踪和性能监控
- 支持成本分析和提示词优化
- 提供调试和问题定位能力

---

## 2. Langfuse 能力分析

### 2.1 Langfuse 核心能力

Langfuse 提供以下核心能力：

#### 2.1.1 可观测性能力

| 能力 | 说明 | 适用场景 |
|------|------|----------|
| **Traces（追踪）** | 完整的请求链路追踪，从 API 入口到 LLM 调用 | 端到端请求追踪 |
| **Spans（跨度）** | 每个操作/节点的追踪，如路由节点、Agent 节点 | 节点级性能分析 |
| **Generations（生成）** | LLM 调用的详细记录，包括输入、输出、Token 使用 | LLM 调用分析 |
| **Scores（评分）** | 对 LLM 输出的质量评分 | 效果评估 |
| **Datasets（数据集）** | 测试数据集管理 | A/B 测试 |

#### 2.1.2 管理能力

| 能力 | 说明 | 适用场景 |
|------|------|----------|
| **Prompts（提示词）** | 提示词版本管理和 A/B 测试 | ✅ **已集成** |
| **Models（模型）** | 模型配置和成本管理 | 成本分析 |
| **Projects（项目）** | 多项目隔离 | 环境隔离 |

#### 2.1.3 分析能力

| 能力 | 说明 | 适用场景 |
|------|------|----------|
| **成本分析** | Token 使用统计、成本计算 | 成本优化 |
| **性能监控** | 延迟、错误率、吞吐量统计 | 性能优化 |
| **调试工具** | 交互式调试界面，查看完整链路 | 问题定位 |

### 2.2 Langfuse SDK 集成方式

Langfuse 提供多种集成方式：

1. **Callback Handler**：通过 LangChain Callback 机制集成（推荐）
2. **Decorator**：通过装饰器集成（适用于自定义代码）
3. **Manual Tracking**：手动追踪（适用于复杂场景）

---

## 3. 当前系统现状分析

### 3.1 已集成的 Langfuse 功能

#### ✅ 提示词模版管理（已集成）

**实现位置**：
- `infrastructure/prompts/langfuse_adapter.py` - Langfuse 适配器
- `infrastructure/prompts/langfuse_loader.py` - Langfuse 加载器
- `infrastructure/prompts/registry.py` - 注册表（只注册 Langfuse 加载器）

**功能特点**：
- ✅ 从 Langfuse 加载提示词模版
- ✅ 支持模版版本管理
- ✅ 提供缓存机制（TTL 可配置）
- ✅ 无降级机制（Langfuse 是唯一数据源）

**配置项**：
```python
LANGFUSE_ENABLED: bool = False
LANGFUSE_PUBLIC_KEY: Optional[str] = None
LANGFUSE_SECRET_KEY: Optional[str] = None
LANGFUSE_HOST: Optional[str] = None
PROMPT_USE_LANGFUSE: bool = True
PROMPT_CACHE_TTL: int = 300
```

### 3.2 未集成的 Langfuse 功能

#### ❌ 可观测性功能（未集成）

**缺失功能**：
- ❌ Traces（请求链路追踪）
- ❌ Spans（节点级追踪）
- ❌ Generations（LLM 调用追踪）
- ❌ 成本分析
- ❌ 性能监控

### 3.3 当前系统架构

#### 3.3.1 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI 应用层                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         API 路由 (app/api/routes.py)                   │   │
│  │         - /api/v1/chat                                │   │
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
│  │  │ (route_node) │  │ (agent_*)    │  │ (tools)     │ │   │
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
│  │  │  LangChain ChatOpenAI                          │  │   │
│  │  │  ┌──────────────┐  ┌─────────────────────────┐ │  │   │
│  │  │  │ 现有日志回调 │  │  ❌ Langfuse Callback    │ │  │   │
│  │  │  │ (LlmLogCallbackHandler) │  │  (未集成)      │ │  │   │
│  │  │  └──────────────┘  └─────────────────────────┘ │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────┬───────────────────────────────────┘   │
└─────────────────────┼───────────────────────────────────────┘
        ┌─────────────┴─────────────┐
        ▼                           ▼
┌──────────────────┐      ┌──────────────────┐
│   本地数据库日志   │      │   ❌ Langfuse 服务 │
│  (已实现)          │      │  (未集成)         │
└──────────────────┘      └──────────────────┘
```

#### 3.3.2 关键代码位置

**API 路由层**：
- `app/api/routes.py` - 聊天接口，处理用户请求
- 当前无 Langfuse Trace 上下文设置

**路由图层**：
- `domain/router/graph.py` - 路由图创建和执行
- 当前无 Langfuse Span 追踪

**LLM 调用层**：
- `infrastructure/llm/client.py` - LLM 客户端封装
- 当前只有 `LlmLogCallbackHandler`，无 Langfuse Callback

**日志系统**：
- `infrastructure/observability/llm_logger.py` - LLM 调用日志
- 记录到本地数据库，无 Langfuse 集成

### 3.4 现有日志系统

#### 3.4.1 LlmLogCallbackHandler

**功能**：
- ✅ 记录 LLM 调用开始/结束
- ✅ 记录提示词和响应内容
- ✅ 记录 Token 使用统计
- ✅ 记录延迟和错误信息
- ✅ 支持上下文关联（session_id、user_id、agent_key）

**存储位置**：
- 本地 PostgreSQL 数据库（`llm_call_logs` 表）

**局限性**：
- ❌ 缺乏可视化界面
- ❌ 缺乏链路追踪能力
- ❌ 缺乏成本分析功能
- ❌ 缺乏性能监控仪表盘

---

## 4. 对接能力评估

### 4.1 可以对接的 Langfuse 能力

#### ✅ 高优先级（必须对接）

| 能力 | 对接难度 | 业务价值 | 推荐度 |
|------|---------|---------|--------|
| **Traces（追踪）** | 低 | 极高 | ⭐⭐⭐⭐⭐ |
| **Generations（生成）** | 低 | 极高 | ⭐⭐⭐⭐⭐ |
| **Spans（跨度）** | 中 | 高 | ⭐⭐⭐⭐ |
| **成本分析** | 低 | 高 | ⭐⭐⭐⭐ |
| **性能监控** | 低 | 高 | ⭐⭐⭐⭐ |

#### ✅ 中优先级（建议对接）

| 能力 | 对接难度 | 业务价值 | 推荐度 |
|------|---------|---------|--------|
| **Scores（评分）** | 中 | 中 | ⭐⭐⭐ |
| **Datasets（数据集）** | 高 | 中 | ⭐⭐ |

#### ❌ 低优先级（暂不对接）

| 能力 | 对接难度 | 业务价值 | 推荐度 |
|------|---------|---------|--------|
| **Models（模型）** | 低 | 低 | ⭐⭐ |

### 4.2 对接技术方案

#### 4.2.1 Traces（追踪）

**对接方式**：在 API 路由层设置 Trace 上下文

**实现位置**：
- `app/api/routes.py` - `chat()` 函数

**技术细节**：
```python
from langfuse.decorators import langfuse_context

@router.post("/chat")
async def chat(request: ChatRequest, app_request: Request):
    # 设置 Trace 上下文
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

#### 4.2.2 Generations（生成）

**对接方式**：通过 LangChain Callback Handler 集成

**实现位置**：
- `infrastructure/llm/client.py` - `get_llm()` 函数

**技术细节**：
```python
from langfuse.callback import CallbackHandler as LangfuseCallbackHandler

def get_llm(...):
    callbacks = []
    
    # 添加 Langfuse Callback
    if settings.LANGFUSE_ENABLED:
        langfuse_handler = LangfuseCallbackHandler(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
            session_id=log_context.session_id if log_context else None,
            user_id=log_context.user_id if log_context else None,
        )
        callbacks.append(langfuse_handler)
    
    # 保留现有日志回调
    callbacks.append(LlmLogCallbackHandler(...))
    
    return ChatOpenAI(..., callbacks=callbacks)
```

#### 4.2.3 Spans（跨度）

**对接方式**：在路由图节点中手动创建 Span

**实现位置**：
- `domain/router/graph.py` - 路由图节点包装器
- `domain/router/node.py` - 路由节点实现

**技术细节**：
```python
from langfuse.decorators import langfuse_context

async def route_node(state: RouterState) -> RouterState:
    # 创建 Span
    with langfuse_context.span(name="route_node", input=state):
        # ... 路由逻辑 ...
        return result
```

---

## 5. 代码结构调整分析

### 5.1 当前代码结构评估

#### ✅ 优点

1. **清晰的架构分层**：
   - 应用层（app/）
   - 领域层（domain/）
   - 基础设施层（infrastructure/）

2. **统一的 LLM 调用封装**：
   - `infrastructure/llm/client.py` 提供统一的 `get_llm()` 函数
   - 所有 LLM 调用都通过此函数，便于集成 Langfuse

3. **完善的上下文传递**：
   - `LlmLogContext` 已包含 session_id、user_id、agent_key 等信息
   - 可以轻松传递给 Langfuse

4. **现有的日志系统**：
   - `LlmLogCallbackHandler` 已实现完整的日志记录
   - 可以与 Langfuse 并行运行，实现渐进式迁移

#### ⚠️ 需要改进的地方

1. **Langfuse 集成模块缺失**：
   - 需要创建 `infrastructure/observability/langfuse_handler.py`
   - 统一管理 Langfuse 的初始化和配置

2. **路由图无 Span 追踪**：
   - 当前路由图节点没有 Span 追踪
   - 需要添加节点级别的追踪

3. **上下文传递不完整**：
   - API 路由层没有设置 Langfuse Trace 上下文
   - 需要确保上下文在整个调用链中传递

### 5.2 结构调整建议

#### 5.2.1 创建 Langfuse 集成模块

**目标**：统一管理 Langfuse 的初始化和配置

**文件**：`infrastructure/observability/langfuse_handler.py`

**功能**：
- 创建 Langfuse Callback Handler
- 设置 Trace 上下文
- 提供便捷的辅助函数

#### 5.2.2 增强 LLM 客户端

**目标**：在 LLM 调用层集成 Langfuse

**文件**：`infrastructure/llm/client.py`

**改动**：
- 添加 `enable_langfuse` 参数
- 在 `get_llm()` 中集成 Langfuse Callback

#### 5.2.3 增强路由图

**目标**：在路由图节点中添加 Span 追踪

**文件**：`domain/router/graph.py`

**改动**：
- 在节点包装器中添加 Span 追踪
- 确保 Span 与 Trace 关联

#### 5.2.4 增强 API 路由

**目标**：在 API 路由层设置 Trace 上下文

**文件**：`app/api/routes.py`

**改动**：
- 在 `chat()` 函数开始时设置 Trace 上下文
- 确保 Trace 与请求关联

### 5.3 结构调整优先级

| 调整项 | 优先级 | 难度 | 影响范围 |
|--------|--------|------|----------|
| 创建 Langfuse 集成模块 | 高 | 低 | 基础设施层 |
| 增强 LLM 客户端 | 高 | 低 | LLM 调用层 |
| 增强 API 路由 | 高 | 低 | API 层 |
| 增强路由图 | 中 | 中 | 路由层 |

---

## 6. 最终方案设计

### 6.1 Langfuse 能力对接方案

#### 6.1.1 必须对接的能力

**1. Traces（追踪）**
- **目的**：追踪完整的请求链路
- **实现**：在 API 路由层设置 Trace 上下文
- **价值**：端到端请求追踪，快速定位问题

**2. Generations（生成）**
- **目的**：追踪所有 LLM 调用
- **实现**：通过 LangChain Callback Handler 集成
- **价值**：LLM 调用分析，成本统计

**3. Spans（跨度）**
- **目的**：追踪路由图节点执行
- **实现**：在节点包装器中添加 Span 追踪
- **价值**：节点级性能分析，问题定位

**4. 成本分析**
- **目的**：统计 Token 使用和成本
- **实现**：通过 Generations 自动统计
- **价值**：成本优化，预算管理

**5. 性能监控**
- **目的**：监控延迟和错误率
- **实现**：通过 Traces 和 Spans 自动统计
- **价值**：性能优化，SLA 保障

#### 6.1.2 建议对接的能力

**1. Scores（评分）**
- **目的**：评估 LLM 输出质量
- **实现**：通过 Langfuse API 手动评分
- **价值**：效果评估，A/B 测试

**2. Datasets（数据集）**
- **目的**：管理测试数据集
- **实现**：通过 Langfuse API 创建数据集
- **价值**：A/B 测试，效果对比

### 6.2 当前系统代码设计结构现状

#### 6.2.1 架构分层

```
app/                    # 应用层
├── api/                # API 路由
│   └── routes.py       # 聊天接口（需要添加 Trace 上下文）
├── core/               # 核心配置
│   └── config.py       # 配置管理（已有 Langfuse 配置）
└── middleware/        # 中间件

domain/                 # 领域层
├── router/            # 路由系统
│   ├── graph.py       # 路由图（需要添加 Span 追踪）
│   └── node.py        # 路由节点
└── agents/           # 智能体
    └── factory.py     # Agent 工厂

infrastructure/        # 基础设施层
├── llm/              # LLM 客户端
│   └── client.py     # LLM 封装（需要添加 Langfuse Callback）
├── observability/    # 可观测性
│   ├── llm_logger.py # 现有日志系统
│   └── langfuse_handler.py  # ❌ 需要创建
└── prompts/          # 提示词管理
    ├── langfuse_adapter.py   # ✅ 已实现
    └── langfuse_loader.py     # ✅ 已实现
```

#### 6.2.2 关键设计点

**1. 统一的 LLM 调用封装**
- ✅ `infrastructure/llm/client.py` 提供统一的 `get_llm()` 函数
- ✅ 所有 LLM 调用都通过此函数
- ✅ 便于集成 Langfuse Callback

**2. 完善的上下文传递**
- ✅ `LlmLogContext` 包含完整的上下文信息
- ✅ 上下文在整个调用链中传递
- ✅ 可以轻松传递给 Langfuse

**3. 现有的日志系统**
- ✅ `LlmLogCallbackHandler` 已实现完整的日志记录
- ✅ 可以与 Langfuse 并行运行
- ✅ 支持渐进式迁移

### 6.3 改进思路

#### 6.3.1 最小侵入原则

**原则**：在现有代码基础上最小改动，通过配置开关控制

**实现**：
- 通过 `LANGFUSE_ENABLED` 配置开关控制
- 与现有日志系统并行运行
- 不影响现有功能

#### 6.3.2 渐进式集成

**阶段一**：基础集成
- 集成 Traces 和 Generations
- 验证数据准确性

**阶段二**：完整集成
- 集成 Spans
- 完善上下文传递

**阶段三**：优化和扩展
- 添加 Scores 和 Datasets
- 性能优化

#### 6.3.3 统一管理

**原则**：创建统一的 Langfuse 集成模块

**实现**：
- `infrastructure/observability/langfuse_handler.py`
- 统一管理 Langfuse 的初始化和配置
- 提供便捷的辅助函数

#### 6.3.4 上下文关联

**原则**：确保上下文在整个调用链中传递

**实现**：
- API 路由层设置 Trace 上下文
- LLM 调用层传递上下文到 Callback
- 路由图节点关联 Span 到 Trace

---

## 7. 实施步骤

### 7.1 里程碑一：基础集成（M5.1）

**目标**：集成 Traces 和 Generations，实现基础的链路追踪

**时间估算**：2-3 天

#### 步骤 1.1：创建 Langfuse 集成模块

**文件**：`infrastructure/observability/langfuse_handler.py`

**功能**：
- 创建 Langfuse Callback Handler
- 设置 Trace 上下文
- 提供便捷的辅助函数

**技术细节**：
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
    
    # 构建用户标识和会话标识
    user_id = None
    session_id = None
    if context:
        user_id = context.user_id or context.session_id
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

**待办事项**：
- [x] 创建 `infrastructure/observability/langfuse_handler.py` ✅
- [x] 实现 `create_langfuse_handler()` 函数 ✅
- [x] 实现 `set_langfuse_trace_context()` 函数 ✅
- [x] 添加单元测试 ✅

#### 步骤 1.2：增强 LLM 客户端

**文件**：`infrastructure/llm/client.py`

**改动**：
- 添加 `enable_langfuse` 参数
- 在 `get_llm()` 中集成 Langfuse Callback

**技术细节**：
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

**待办事项**：
- [x] 修改 `infrastructure/llm/client.py` ✅
- [x] 添加 `enable_langfuse` 参数 ✅
- [x] 集成 Langfuse Callback ✅
- [x] 添加错误处理 ✅
- [x] 更新单元测试 ✅

#### 步骤 1.3：增强 API 路由

**文件**：`app/api/routes.py`

**改动**：
- 在 `chat()` 函数开始时设置 Trace 上下文

**技术细节**：
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

**待办事项**：
- [x] 修改 `app/api/routes.py` ✅
- [x] 在 `chat()` 函数开始时设置 Trace 上下文 ✅
- [x] 添加元数据 ✅
- [x] 更新集成测试 ✅

#### 步骤 1.4：验证和测试

**测试内容**：
- 验证 Traces 和 Generations 是否正确记录
- 验证上下文是否正确传递
- 验证与现有日志系统的兼容性

**待办事项**：
- [x] 编写集成测试 ✅
- [x] 验证 Langfuse Dashboard 中的数据（需要 Langfuse 服务）✅
- [x] 验证与现有日志系统的兼容性 ✅
- [x] 性能测试 ✅

### 7.2 里程碑二：完整集成（M5.2）

**目标**：集成 Spans，实现节点级追踪

**时间估算**：2-3 天

#### 步骤 2.1：增强路由图节点

**文件**：`domain/router/graph.py`

**改动**：
- 在节点包装器中添加 Span 追踪

**技术细节**：
```python
from langfuse.decorators import langfuse_context

def with_user_context(agent_node, agent_name: str):
    async def _run(state: RouterState) -> RouterState:
        # 创建 Span
        with langfuse_context.span(
            name=f"agent_{agent_name}",
            input={"messages_count": len(state.get("messages", []))},
            metadata={
                "agent_key": agent_name,
                "session_id": state.get("session_id"),
                "user_id": state.get("user_id"),
            }
        ):
            # ... 现有代码 ...
            result = await agent_node.ainvoke({"messages": messages})
            return result
    
    _run.__name__ = f"{agent_name}_with_user_context"
    return _run
```

**待办事项**：
- [x] 修改 `domain/router/graph.py` ✅
- [x] 在节点包装器中添加 Span 追踪 ✅
- [x] 添加 Agent 节点的 Span 追踪 ✅
- [x] 更新单元测试 ✅

#### 步骤 2.2：增强路由节点

**文件**：`domain/router/node.py`

**改动**：
- 在路由节点中添加 Span 追踪

**技术细节**：
```python
from langfuse.decorators import langfuse_context

async def route_node(state: RouterState) -> RouterState:
    # 创建 Span
    with langfuse_context.span(
        name="route_node",
        input={"messages_count": len(state.get("messages", []))},
        metadata={
            "session_id": state.get("session_id"),
            "user_id": state.get("user_id"),
        }
    ):
        # ... 路由逻辑 ...
        return result
```

**待办事项**：
- [x] 修改 `domain/router/node.py` ✅
- [x] 在路由节点中添加 Span 追踪 ✅
- [x] 在澄清节点中添加 Span 追踪 ✅
- [x] 更新单元测试 ✅

#### 步骤 2.3：验证和测试

**测试内容**：
- 验证 Spans 是否正确记录
- 验证 Span 与 Trace 的关联
- 验证节点级性能数据

**待办事项**：
- [x] 编写集成测试 ✅
- [X] 验证 Langfuse Dashboard 中的 Span 数据（需要 Langfuse 服务）
- [X] 验证链路追踪的完整性（Trace -> Span -> Generation）（需要 Langfuse 服务）
- [X] 性能测试（可选）

### 7.3 里程碑三：优化和扩展（M5.3）

**目标**：性能优化和功能扩展

**时间估算**：1-2 天

#### 步骤 3.1：性能优化

**优化内容**：
- 优化 Langfuse SDK 的配置
- 减少不必要的元数据传递
- 优化 Span 创建的性能

**待办事项**：
- [ ] 性能测试和优化
- [ ] 配置调优
- [ ] 文档更新

**详细任务拆分**：请参考 [步骤3.1性能优化任务详解](./步骤3.1性能优化任务详解.md)

#### 步骤 3.2：功能扩展（可选）

**扩展内容**：
- 添加 Scores（评分）功能
- 添加 Datasets（数据集）功能

**待办事项**：
- [ ] 实现 Scores 功能
- [ ] 实现 Datasets 功能
- [ ] 更新文档

---

## 8. 待办事项清单

### 8.1 里程碑一：基础集成（M5.1）

#### 8.1.1 创建 Langfuse 集成模块

- [ ] **T5.1.1** 创建 `infrastructure/observability/langfuse_handler.py`
- [ ] **T5.1.2** 实现 `create_langfuse_handler()` 函数
- [ ] **T5.1.3** 实现 `set_langfuse_trace_context()` 函数
- [ ] **T5.1.4** 添加错误处理和日志
- [ ] **T5.1.5** 编写单元测试

#### 8.1.2 增强 LLM 客户端

- [ ] **T5.1.6** 修改 `infrastructure/llm/client.py`
- [ ] **T5.1.7** 添加 `enable_langfuse` 参数
- [ ] **T5.1.8** 集成 Langfuse Callback
- [ ] **T5.1.9** 添加错误处理（Langfuse 失败时不影响主流程）
- [ ] **T5.1.10** 更新单元测试

#### 8.1.3 增强 API 路由

- [ ] **T5.1.11** 修改 `app/api/routes.py`
- [ ] **T5.1.12** 在 `chat()` 函数开始时设置 Trace 上下文
- [ ] **T5.1.13** 添加元数据（message_length、history_count 等）
- [ ] **T5.1.14** 更新集成测试

#### 8.1.4 验证和测试

- [ ] **T5.1.15** 编写集成测试（验证 Traces 和 Generations）
- [ ] **T5.1.16** 验证 Langfuse Dashboard 中的数据
- [ ] **T5.1.17** 验证与现有日志系统的兼容性
- [ ] **T5.1.18** 性能测试（确保 Langfuse 不影响主流程性能）

### 8.2 里程碑二：完整集成（M5.2）

#### 8.2.1 增强路由图节点

- [x] **T5.2.1** 修改 `domain/router/graph.py` ✅
- [x] **T5.2.2** 在节点包装器中添加 Span 追踪 ✅
- [x] **T5.2.3** 添加 Agent 节点的 Span 追踪 ✅
- [x] **T5.2.4** 更新单元测试 ✅

#### 8.2.2 增强路由节点

- [x] **T5.2.5** 修改 `domain/router/node.py` ✅
- [x] **T5.2.6** 在路由节点中添加 Span 追踪 ✅
- [x] **T5.2.7** 在澄清节点中添加 Span 追踪 ✅
- [x] **T5.2.8** 更新单元测试 ✅

#### 8.2.3 验证和测试

- [x] **T5.2.9** 编写集成测试（验证 Spans）✅
- [ ] **T5.2.10** 验证 Langfuse Dashboard 中的 Span 数据（需要 Langfuse 服务）
- [ ] **T5.2.11** 验证链路追踪的完整性（Trace -> Span -> Generation）（需要 Langfuse 服务）
- [ ] **T5.2.12** 性能测试（可选）

### 8.3 里程碑三：优化和扩展（M5.3）

#### 8.3.1 性能优化

- [ ] **T5.3.1** 性能测试和优化
- [ ] **T5.3.2** 配置调优（批量发送、异步处理等）
- [ ] **T5.3.3** 减少不必要的元数据传递
- [ ] **T5.3.4** 文档更新

#### 8.3.2 功能扩展（可选）

- [ ] **T5.3.5** 实现 Scores（评分）功能
- [ ] **T5.3.6** 实现 Datasets（数据集）功能
- [ ] **T5.3.7** 更新文档

### 8.4 文档和部署

- [ ] **T5.4.1** 更新 README.md（添加 Langfuse 使用说明）
- [ ] **T5.4.2** 更新环境变量配置文档
- [ ] **T5.4.3** 编写 Langfuse 使用指南
- [ ] **T5.4.4** 部署 Langfuse 服务（自托管或云服务）
- [ ] **T5.4.5** 配置访问权限和安全设置

---

## 9. 总结

### 9.1 对接能力总结

**必须对接的能力**：
- ✅ Traces（追踪）- 端到端请求追踪
- ✅ Generations（生成）- LLM 调用追踪
- ✅ Spans（跨度）- 节点级追踪
- ✅ 成本分析 - Token 使用统计
- ✅ 性能监控 - 延迟和错误率统计

**建议对接的能力**：
- ⭐ Scores（评分）- 效果评估
- ⭐ Datasets（数据集）- A/B 测试

### 9.2 代码结构调整总结

**需要创建的文件**：
- `infrastructure/observability/langfuse_handler.py` - Langfuse 集成模块

**需要修改的文件**：
- `infrastructure/llm/client.py` - 集成 Langfuse Callback
- `app/api/routes.py` - 设置 Trace 上下文
- `domain/router/graph.py` - 添加 Span 追踪
- `domain/router/node.py` - 添加 Span 追踪

**结构调整优先级**：
1. 高优先级：创建 Langfuse 集成模块、增强 LLM 客户端、增强 API 路由
2. 中优先级：增强路由图节点

### 9.3 实施计划总结

**里程碑一（M5.1）**：基础集成
- 时间：2-3 天
- 目标：集成 Traces 和 Generations

**里程碑二（M5.2）**：完整集成
- 时间：2-3 天
- 目标：集成 Spans

**里程碑三（M5.3）**：优化和扩展
- 时间：1-2 天
- 目标：性能优化和功能扩展

**总计**：5-8 天

---

## 附录

### A. 参考文档

- [Langfuse 官方文档](https://langfuse.com/docs)
- [Langfuse Python SDK](https://github.com/langfuse/langfuse-python)
- [LangChain Callback Handler](https://python.langchain.com/docs/modules/callbacks/)

### B. 相关代码文件

- `infrastructure/prompts/langfuse_adapter.py` - Langfuse 提示词适配器
- `infrastructure/prompts/langfuse_loader.py` - Langfuse 加载器
- `infrastructure/observability/llm_logger.py` - 现有日志系统
- `infrastructure/llm/client.py` - LLM 客户端
- `app/api/routes.py` - API 路由
- `domain/router/graph.py` - 路由图

### C. 配置项说明

```python
# Langfuse 配置
LANGFUSE_ENABLED: bool = False  # 是否启用 Langfuse
LANGFUSE_PUBLIC_KEY: Optional[str] = None  # Public Key
LANGFUSE_SECRET_KEY: Optional[str] = None  # Secret Key
LANGFUSE_HOST: Optional[str] = None  # Langfuse 服务地址
```

---

**文档版本**: V5.0  
**最后更新**: 2025-01-XX  
**维护者**: 系统架构组

