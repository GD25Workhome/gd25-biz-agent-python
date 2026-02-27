"""
工具上下文管理器
使用 contextvars 实现线程安全的运行时信息传递
"""
import contextvars
from typing import Optional

# 创建上下文变量
_token_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'token_id', default=None
)
_session_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'session_id', default=None
)
_trace_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'trace_id', default=None
)


def set_token_id(token_id: str) -> None:
    """
    设置当前上下文的 tokenId
    
    Args:
        token_id: 令牌ID
    """
    _token_id_context.set(token_id)


def get_token_id() -> Optional[str]:
    """
    获取当前上下文的 tokenId
    
    Returns:
        令牌ID，如果未设置则返回 None
    """
    return _token_id_context.get()


def set_session_id(session_id: str) -> None:
    """
    设置当前上下文的 sessionId
    
    Args:
        session_id: 会话ID
    """
    _session_id_context.set(session_id)


def get_session_id() -> Optional[str]:
    """
    获取当前上下文的 sessionId
    
    Returns:
        会话ID，如果未设置则返回 None
    """
    return _session_id_context.get()


def set_trace_id(trace_id: str) -> None:
    """
    设置当前上下文的 traceId
    
    Args:
        trace_id: 追踪ID
    """
    _trace_id_context.set(trace_id)


def get_trace_id() -> Optional[str]:
    """
    获取当前上下文的 traceId
    
    Returns:
        追踪ID，如果未设置则返回 None
    """
    return _trace_id_context.get()


class RuntimeContext:
    """
    运行时上下文管理器（支持多个字段）
    
    使用示例：
        with RuntimeContext(token_id="xxx", session_id="yyy", trace_id="zzz"):
            # 在此上下文中，工具可以获取所有运行时信息
            tool.invoke(...)
    """
    
    def __init__(
        self,
        token_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ):
        """
        初始化上下文管理器
        
        Args:
            token_id: 令牌ID
            session_id: 会话ID
            trace_id: 追踪ID
        """
        self.token_id = token_id
        self.session_id = session_id
        self.trace_id = trace_id
        self._tokens = []
    
    def __enter__(self):
        """进入上下文"""
        if self.token_id is not None:
            self._tokens.append(('token_id', _token_id_context.set(self.token_id)))
        if self.session_id is not None:
            self._tokens.append(('session_id', _session_id_context.set(self.session_id)))
        if self.trace_id is not None:
            self._tokens.append(('trace_id', _trace_id_context.set(self.trace_id)))
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，恢复之前的上下文"""
        for name, token in reversed(self._tokens):
            if name == 'token_id':
                _token_id_context.reset(token)
            elif name == 'session_id':
                _session_id_context.reset(token)
            elif name == 'trace_id':
                _trace_id_context.reset(token)
        return False

