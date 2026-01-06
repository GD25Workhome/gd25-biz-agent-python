"""
工具上下文管理器
使用 contextvars 实现线程安全的 tokenId 传递
"""
import contextvars
from typing import Optional

# 创建上下文变量
_token_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'token_id', default=None
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


class TokenContext:
    """
    工具上下文管理器（上下文管理器协议）
    
    使用示例：
        with TokenContext(token_id="xxx"):
            # 在此上下文中，工具可以获取 token_id
            tool.invoke(...)
    """
    
    def __init__(self, token_id: str):
        """
        初始化上下文管理器
        
        Args:
            token_id: 令牌ID
        """
        self.token_id = token_id
        self._token = None
    
    def __enter__(self):
        """进入上下文"""
        self._token = _token_id_context.set(self.token_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，恢复之前的上下文"""
        if self._token is not None:
            _token_id_context.reset(self._token)
        return False

