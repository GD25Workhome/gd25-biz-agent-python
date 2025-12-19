# LLM调用日志 session_id 和 user_id 缺失问题分析与修复方案 V2

## 一、问题重新分析

### 1.1 核心问题
- `biz_agent_llm_call_logs` 表中部分记录的 `session_id` 和 `user_id` 字段为空

### 1.2 关键洞察

用户的担忧是合理的：
- ❌ **方案V1的问题**：如果通过参数传递所有上下文信息，会导致参数爆炸，工具函数签名会变得非常复杂
- ✅ **理想的方案**：使用类似 token 的 ID（thread_id）作为标识，系统从 thread_id 反向查找需要的信息

### 1.3 当前机制理解

**正确的理解**：
1. LangGraph 使用 `config={"configurable": {"thread_id": session_id}}` 来标识每个执行会话
2. `thread_id` 就是 `session_id`，在整个执行链中都会传递
3. RouterState 中包含 `session_id` 和 `user_id`，但只在节点执行时可用
4. LLM 回调处理器在后台异步执行，无法直接访问 RouterState

**关键点**：
- `thread_id` 就是我们的 "token" - 它在整个执行链中传递
- LangChain 的回调处理器可以通过 `run_manager` 访问到 `config`，从而获取 `thread_id`
- 我们需要建立一个基于 `thread_id` 的上下文存储机制

## 二、新的修复方案

### 2.1 方案核心思路

使用 **上下文存储（Context Store）** 机制：

1. **存储阶段**：在节点执行开始时，将 `session_id` 和 `user_id` 存储到全局上下文存储中（以 `thread_id` 为 key）
2. **读取阶段**：在 LLM 回调处理器中，通过 `thread_id`（从 `run_manager.config` 获取）反向查找上下文信息
3. **清理阶段**：执行完成后清理上下文（可选，也可以设置 TTL 自动过期）

### 2.2 技术实现

#### 2.2.1 创建上下文存储模块

```python
# infrastructure/observability/context_store.py
"""
LLM 调用上下文存储
基于 thread_id 存储和检索执行上下文信息
"""
import asyncio
import time
from typing import Optional, Dict
from dataclasses import dataclass
from infrastructure.observability.llm_logger import LlmLogContext

# 全局上下文存储：thread_id -> LlmLogContext
_context_store: Dict[str, LlmLogContext] = {}
_context_store_lock = asyncio.Lock()

# TTL: 上下文信息保留时间（秒），避免内存泄漏
_CONTEXT_TTL = 3600  # 1小时


@dataclass
class ContextInfo:
    """上下文信息"""
    context: LlmLogContext
    created_at: float  # 时间戳


_context_store_with_ttl: Dict[str, ContextInfo] = {}


def set_context(thread_id: str, context: LlmLogContext) -> None:
    """
    设置上下文信息
    
    Args:
        thread_id: 线程ID（对应 session_id）
        context: 日志上下文
    """
    global _context_store_with_ttl
    _context_store_with_ttl[thread_id] = ContextInfo(
        context=context,
        created_at=time.time()
    )
    # 清理过期上下文（简单实现，也可以使用后台任务）
    _cleanup_expired_contexts()


def get_context(thread_id: str) -> Optional[LlmLogContext]:
    """
    获取上下文信息
    
    Args:
        thread_id: 线程ID（对应 session_id）
        
    Returns:
        日志上下文，如果不存在或已过期则返回 None
    """
    global _context_store_with_ttl
    info = _context_store_with_ttl.get(thread_id)
    if not info:
        return None
    
    # 检查是否过期
    if time.time() - info.created_at > _CONTEXT_TTL:
        del _context_store_with_ttl[thread_id]
        return None
    
    return info.context


def clear_context(thread_id: str) -> None:
    """
    清除上下文信息
    
    Args:
        thread_id: 线程ID
    """
    global _context_store_with_ttl
    _context_store_with_ttl.pop(thread_id, None)


def _cleanup_expired_contexts() -> None:
    """清理过期的上下文信息"""
    global _context_store_with_ttl
    current_time = time.time()
    expired_keys = [
        thread_id for thread_id, info in _context_store_with_ttl.items()
        if current_time - info.created_at > _CONTEXT_TTL
    ]
    for key in expired_keys:
        del _context_store_with_ttl[key]
```

#### 2.2.2 修改 LLM 回调处理器

```python
# infrastructure/observability/llm_logger.py

from infrastructure.observability.context_store import get_context

class LlmLogCallbackHandler(BaseCallbackHandler):
    """LLM 日志回调处理器"""
    
    def __init__(
        self,
        context: Optional[LlmLogContext] = None,  # 保持可选，向后兼容
        # ... 其他参数
    ):
        self.context = context  # 直接传入的上下文（优先使用）
        # ... 其他初始化
    
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[Any], **kwargs: Any) -> None:
        """LLM 开始回调"""
        if not self.log_enabled:
            return
        
        # 尝试获取上下文
        context = self._get_context(kwargs)
        
        # ... 其余代码使用 context
        _run_in_background(_start_log(
            call_id=call_id,
            model=self.model,
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            prompt_snapshot=prompt_snapshot,
            context=context,  # 使用获取到的上下文
            # ...
        ))
    
    def _get_context(self, kwargs: Dict[str, Any]) -> Optional[LlmLogContext]:
        """
        获取执行上下文
        
        优先级：
        1. 直接传入的 context（self.context）
        2. 从 kwargs 的 metadata 或 tags 中获取 thread_id，然后从上下文存储中查找
        3. 返回 None
        
        Args:
            kwargs: 回调参数
            
        Returns:
            日志上下文
        """
        # 优先级1: 直接传入的上下文
        if self.context:
            return self.context
        
        # 优先级2: 从 kwargs 中获取 thread_id
        try:
            # 方式1: 从 metadata 中获取
            metadata = kwargs.get("metadata") or {}
            thread_id = metadata.get("thread_id") or metadata.get("session_id")
            
            # 方式2: 如果 metadata 中没有，尝试从 parent_run_id 关联的上下文中查找
            # 注意：这种方式需要额外的实现，暂时跳过
            
            if thread_id:
                # 从上下文存储中查找
                context = get_context(thread_id)
                if context:
                    return context
        except Exception as e:
            logger.debug(f"从 kwargs 获取上下文失败: {e}")
        
        # 如果都获取不到，返回 None（日志记录时字段为空）
        return None
```

#### 2.2.3 在节点执行时设置上下文

```python
# domain/router/node.py

from infrastructure.observability.context_store import set_context
from infrastructure.observability.llm_logger import LlmLogContext

def route_node(state: RouterState) -> RouterState:
    """路由节点"""
    messages = state.get("messages", [])
    session_id = state.get("session_id")
    user_id = state.get("user_id")
    
    # 设置上下文信息（如果 thread_id 存在）
    if session_id:
        context = LlmLogContext(
            session_id=session_id,
            user_id=user_id,
            agent_key="router_tools"
        )
        set_context(session_id, context)  # thread_id = session_id
    
    # ... 其余代码


def clarify_intent_node(state: RouterState) -> RouterState:
    """澄清节点"""
    messages = state.get("messages", [])
    session_id = state.get("session_id")
    user_id = state.get("user_id")
    
    # 设置上下文信息
    if session_id:
        context = LlmLogContext(
            session_id=session_id,
            user_id=user_id,
            agent_key="router_tools"
        )
        set_context(session_id, context)
    
    # ... 其余代码
```

```python
# domain/router/graph.py

def with_user_context(agent_node, agent_name: str):
    """智能体包装器"""
    async def _run(state: RouterState) -> RouterState:
        messages = state.get("messages", [])
        user_id = state.get("user_id")
        session_id = state.get("session_id")
        
        # 设置上下文信息
        if session_id:
            from infrastructure.observability.context_store import set_context
            from infrastructure.observability.llm_logger import LlmLogContext
            
            context = LlmLogContext(
                session_id=session_id,
                user_id=user_id,
                agent_key=agent_name
            )
            set_context(session_id, context)
        
        # ... 其余代码
```

### 2.2.4 在调用 LLM 时传递 thread_id（可选增强）

如果 LangChain 的回调处理器无法直接从 config 获取 thread_id，我们可以通过以下方式增强：

```python
# infrastructure/llm/client.py

def get_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    log_context: Optional[LlmLogContext] = None,
    enable_logging: Optional[bool] = None,
    thread_id: Optional[str] = None,  # 新增：显式传入 thread_id
    **kwargs
) -> BaseChatModel:
    """获取 LLM 客户端实例"""
    # ... 现有代码 ...
    
    callbacks: List[Any] = list(kwargs.pop("callbacks", []) or [])
    if log_enabled:
        # 如果没有直接传入 log_context，尝试从 thread_id 查找
        if not log_context and thread_id:
            from infrastructure.observability.context_store import get_context
            log_context = get_context(thread_id)
        
        callbacks.append(
            LlmLogCallbackHandler(
                context=log_context,
                # ... 其他参数
            )
        )
    
    # 如果需要在回调处理器中访问 thread_id，可以通过 metadata 传递
    if thread_id and "metadata" not in kwargs:
        kwargs["metadata"] = {"thread_id": thread_id}
    
    # ... 其余代码
```

然后在节点中调用时传入 thread_id：

```python
# domain/router/tools/router_tools.py

def identify_intent(messages: list[BaseMessage], config: Optional[Dict] = None) -> Dict[str, Any]:
    # 从 config 中提取 thread_id（如果 LangGraph 传递了的话）
    thread_id = None
    if config:
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
    
    # 调用 LLM 时传入 thread_id
    llm = get_llm(
        temperature=settings.LLM_TEMPERATURE_INTENT,
        thread_id=thread_id  # 传入 thread_id
    )
    # ... 其余代码
```

**注意**：这个增强方案需要修改工具函数的调用方式。如果 LangGraph 的工具调用不支持传递 config 参数，可能需要使用其他方式。

## 三、方案优势

### 3.1 优点

1. ✅ **避免参数爆炸**：工具函数签名保持不变，不需要传递额外参数
2. ✅ **基于 token 查找**：使用 `thread_id`（session_id）作为标识，从存储中反向查找
3. ✅ **解耦设计**：工具层和日志层解耦，工具函数不需要感知日志记录
4. ✅ **向后兼容**：保留直接传入 context 的方式，支持旧代码
5. ✅ **自动清理**：通过 TTL 机制自动清理过期上下文，避免内存泄漏

### 3.2 执行流程

```
1. API 请求 (session_id, user_id)
   └─> 构建 RouterState
        └─> 执行 route_node
             └─> set_context(thread_id=session_id, context={session_id, user_id})
                  └─> 调用 identify_intent 工具
                       └─> 工具内部调用 get_llm()
                            └─> LLM 回调处理器 on_llm_start
                                 └─> get_context(thread_id) ← 从存储中查找
                                      └─> 记录日志（包含 session_id, user_id）
```

## 四、实施步骤

1. **创建上下文存储模块** (`infrastructure/observability/context_store.py`)
   - 实现基于 thread_id 的存储和查找
   - 实现 TTL 清理机制

2. **修改 LLM 回调处理器** (`infrastructure/observability/llm_logger.py`)
   - 修改 `_get_context()` 方法，支持从上下文存储中查找
   - 保持向后兼容（优先使用直接传入的 context）

3. **在节点执行时设置上下文** (`domain/router/node.py` 和 `domain/router/graph.py`)
   - 在 `route_node` 中设置上下文
   - 在 `clarify_intent_node` 中设置上下文
   - 在 `with_user_context` 包装器中设置上下文

4. **测试验证**
   - 验证日志记录中包含 session_id 和 user_id
   - 验证多并发场景下的上下文隔离
   - 验证上下文自动清理机制

## 五、注意事项

1. **线程安全**：如果有多线程/多进程环境，需要考虑使用线程安全的存储机制（可以使用 Redis 或数据库）
2. **内存管理**：通过 TTL 机制避免内存泄漏，也可以考虑使用 LRU 缓存
3. **性能影响**：字典查找的性能开销很小，可以忽略
4. **错误处理**：如果上下文查找失败，记录警告但不影响主流程

## 六、扩展方案（可选）

如果未来需要更强大的上下文管理，可以考虑：

1. **使用 Redis 作为存储后端**：支持分布式环境和持久化
2. **使用 contextvars**：利用 Python 的上下文变量机制（但需要注意异步环境）
3. **集成到 LangGraph 的 config**：直接在 config 中存储上下文信息（需要确认 LangChain 是否支持）

## 七、总结

这个方案：
- ✅ 符合用户的设计理念（基于 token 反向查找）
- ✅ 避免了参数爆炸问题
- ✅ 保持了代码的简洁性和可维护性
- ✅ 向后兼容，不影响现有代码
