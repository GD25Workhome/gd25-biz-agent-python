"""
上下文管理器：管理上下文的生命周期
负责创建、获取和清理SessionContext和TokenContext
"""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ContextManager:
    """
    上下文管理器：管理上下文生命周期
    
    负责创建、获取和清理SessionContext和TokenContext，
    支持会话级别的上下文管理和Token级别的上下文管理。
    """
    
    def __init__(self):
        """
        初始化上下文管理器
        """
        self._session_contexts: Dict[str, Any] = {}
        self._token_contexts: Dict[str, Any] = {}
        logger.debug("创建ContextManager实例")
    
    def create_session_context(self, session_id: str) -> Dict[str, Any]:
        """
        创建聊天上下文
        
        Args:
            session_id: 会话ID（对应一个聊天对话框）
            
        Returns:
            Dict[str, Any]: 创建的聊天上下文字典
        """
        if session_id in self._session_contexts:
            logger.warning(f"SessionContext已存在，将覆盖: session_id={session_id}")
        
        context: Dict[str, Any] = {}
        self._session_contexts[session_id] = context
        logger.info(f"创建SessionContext: session_id={session_id}")
        return context
    
    def get_session_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取聊天上下文
        
        Args:
            session_id: 会话ID（对应一个聊天对话框）
            
        Returns:
            Dict[str, Any]: 聊天上下文字典，如果不存在则返回None
        """
        context = self._session_contexts.get(session_id)
        if context is None:
            logger.debug(f"SessionContext不存在: session_id={session_id}")
        return context
    
    def get_or_create_session_context(self, session_id: str) -> Dict[str, Any]:
        """
        获取或创建聊天上下文
        
        Args:
            session_id: 会话ID（对应一个聊天对话框）
            
        Returns:
            Dict[str, Any]: 聊天上下文字典
        """
        context = self.get_session_context(session_id)
        if context is None:
            context = self.create_session_context(session_id)
        return context
    
    def create_token_context(self, token_id: str) -> Dict[str, Any]:
        """
        创建Token上下文
        
        Args:
            token_id: Token ID
            
        Returns:
            Dict[str, Any]: 创建的Token上下文字典（如果已存在则返回现有实例）
        """
        if token_id not in self._token_contexts:
            context: Dict[str, Any] = {
                "token_id": token_id,
            }
            self._token_contexts[token_id] = context
            logger.info(f"创建TokenContext: token_id={token_id}")
        else:
            context = self._token_contexts[token_id]
            logger.debug(f"TokenContext已存在，返回现有实例: token_id={token_id}")
        
        return context
    
    def get_token_context(self, token_id: str) -> Optional[Dict[str, Any]]:
        """
        获取Token上下文
        
        Args:
            token_id: Token ID
            
        Returns:
            Dict[str, Any]: Token上下文字典，如果不存在则返回None
        """
        context = self._token_contexts.get(token_id)
        if context is None:
            logger.debug(f"TokenContext不存在: token_id={token_id}")
        return context
    
    def get_or_create_token_context(self, token_id: str) -> Dict[str, Any]:
        """
        获取或创建Token上下文
        
        Args:
            token_id: Token ID
            
        Returns:
            Dict[str, Any]: Token上下文字典
        """
        context = self.get_token_context(token_id)
        if context is None:
            context = self.create_token_context(token_id)
        return context
    
    def clear_session_context(self, session_id: str) -> None:
        """
        清理聊天上下文
        
        Args:
            session_id: 会话ID（对应一个聊天对话框）
        """
        if session_id in self._session_contexts:
            del self._session_contexts[session_id]
            logger.info(f"清理SessionContext: session_id={session_id}")
        else:
            logger.debug(f"SessionContext不存在，无需清理: session_id={session_id}")
    
    def clear_token_context(self, token_id: str) -> None:
        """
        清理Token上下文
        
        Args:
            token_id: Token ID
        """
        if token_id in self._token_contexts:
            del self._token_contexts[token_id]
            logger.info(f"清理TokenContext: token_id={token_id}")
        else:
            logger.debug(f"TokenContext不存在，无需清理: token_id={token_id}")
    
    def clear_all_session_contexts(self) -> None:
        """
        清理所有聊天上下文
        """
        count = len(self._session_contexts)
        self._session_contexts.clear()
        logger.info(f"清理所有SessionContext: count={count}")
    
    def clear_all_token_contexts(self) -> None:
        """
        清理所有Token上下文
        """
        count = len(self._token_contexts)
        self._token_contexts.clear()
        logger.info(f"清理所有TokenContext: count={count}")
    
    def clear_all(self) -> None:
        """
        清理所有上下文
        """
        self.clear_all_session_contexts()
        self.clear_all_token_contexts()
        logger.info("清理所有上下文")
    
    def get_session_context_count(self) -> int:
        """
        获取聊天上下文数量
        
        Returns:
            int: 聊天上下文数量
        """
        return len(self._session_contexts)
    
    def get_token_context_count(self) -> int:
        """
        获取Token上下文数量
        
        Returns:
            int: Token上下文数量
        """
        return len(self._token_contexts)
    
    def __repr__(self) -> str:
        """返回对象的字符串表示"""
        return f"ContextManager(session_contexts={len(self._session_contexts)}, token_contexts={len(self._token_contexts)})"


# 创建全局上下文管理器实例（单例模式）
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """
    获取全局上下文管理器实例（单例模式）
    
    Returns:
        ContextManager: 全局上下文管理器实例
    """
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
        logger.info("创建全局ContextManager实例")
    return _context_manager

