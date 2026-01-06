"""
上下文管理器：管理上下文的生命周期
负责创建、获取和清理FlowContext和UserContext
"""
import logging
from typing import Optional, Dict

from backend.domain.context.flow_context import FlowContext
from backend.domain.context.user_context import UserContext

logger = logging.getLogger(__name__)


class ContextManager:
    """
    上下文管理器：管理上下文生命周期
    
    负责创建、获取和清理FlowContext和UserContext，
    支持流程级别的上下文管理和用户级别的上下文管理。
    """
    
    def __init__(self):
        """
        初始化上下文管理器
        """
        self._flow_contexts: Dict[str, FlowContext] = {}
        self._user_contexts: Dict[str, UserContext] = {}
        logger.debug("创建ContextManager实例")
    
    def create_flow_context(self, flow_id: str) -> FlowContext:
        """
        创建流程上下文
        
        Args:
            flow_id: 流程ID（通常使用session_id）
            
        Returns:
            FlowContext: 创建的流程上下文实例
        """
        if flow_id in self._flow_contexts:
            logger.warning(f"FlowContext已存在，将覆盖: flow_id={flow_id}")
        
        context = FlowContext()
        self._flow_contexts[flow_id] = context
        logger.info(f"创建FlowContext: flow_id={flow_id}")
        return context
    
    def get_flow_context(self, flow_id: str) -> Optional[FlowContext]:
        """
        获取流程上下文
        
        Args:
            flow_id: 流程ID（通常使用session_id）
            
        Returns:
            FlowContext: 流程上下文实例，如果不存在则返回None
        """
        context = self._flow_contexts.get(flow_id)
        if context is None:
            logger.debug(f"FlowContext不存在: flow_id={flow_id}")
        return context
    
    def get_or_create_flow_context(self, flow_id: str) -> FlowContext:
        """
        获取或创建流程上下文
        
        Args:
            flow_id: 流程ID（通常使用session_id）
            
        Returns:
            FlowContext: 流程上下文实例
        """
        context = self.get_flow_context(flow_id)
        if context is None:
            context = self.create_flow_context(flow_id)
        return context
    
    def create_user_context(self, user_id: str) -> UserContext:
        """
        创建用户上下文
        
        Args:
            user_id: 用户ID（通常使用token_id）
            
        Returns:
            UserContext: 创建的用户上下文实例（如果已存在则返回现有实例）
        """
        if user_id not in self._user_contexts:
            context = UserContext(user_id)
            self._user_contexts[user_id] = context
            logger.info(f"创建UserContext: user_id={user_id}")
        else:
            context = self._user_contexts[user_id]
            logger.debug(f"UserContext已存在，返回现有实例: user_id={user_id}")
        
        return context
    
    def get_user_context(self, user_id: str) -> Optional[UserContext]:
        """
        获取用户上下文
        
        Args:
            user_id: 用户ID（通常使用token_id）
            
        Returns:
            UserContext: 用户上下文实例，如果不存在则返回None
        """
        context = self._user_contexts.get(user_id)
        if context is None:
            logger.debug(f"UserContext不存在: user_id={user_id}")
        return context
    
    def get_or_create_user_context(self, user_id: str) -> UserContext:
        """
        获取或创建用户上下文
        
        Args:
            user_id: 用户ID（通常使用token_id）
            
        Returns:
            UserContext: 用户上下文实例
        """
        context = self.get_user_context(user_id)
        if context is None:
            context = self.create_user_context(user_id)
        return context
    
    def clear_flow_context(self, flow_id: str) -> None:
        """
        清理流程上下文
        
        Args:
            flow_id: 流程ID（通常使用session_id）
        """
        if flow_id in self._flow_contexts:
            del self._flow_contexts[flow_id]
            logger.info(f"清理FlowContext: flow_id={flow_id}")
        else:
            logger.debug(f"FlowContext不存在，无需清理: flow_id={flow_id}")
    
    def clear_user_context(self, user_id: str) -> None:
        """
        清理用户上下文
        
        Args:
            user_id: 用户ID（通常使用token_id）
        """
        if user_id in self._user_contexts:
            del self._user_contexts[user_id]
            logger.info(f"清理UserContext: user_id={user_id}")
        else:
            logger.debug(f"UserContext不存在，无需清理: user_id={user_id}")
    
    def clear_all_flow_contexts(self) -> None:
        """
        清理所有流程上下文
        """
        count = len(self._flow_contexts)
        self._flow_contexts.clear()
        logger.info(f"清理所有FlowContext: count={count}")
    
    def clear_all_user_contexts(self) -> None:
        """
        清理所有用户上下文
        """
        count = len(self._user_contexts)
        self._user_contexts.clear()
        logger.info(f"清理所有UserContext: count={count}")
    
    def clear_all(self) -> None:
        """
        清理所有上下文
        """
        self.clear_all_flow_contexts()
        self.clear_all_user_contexts()
        logger.info("清理所有上下文")
    
    def get_flow_context_count(self) -> int:
        """
        获取流程上下文数量
        
        Returns:
            int: 流程上下文数量
        """
        return len(self._flow_contexts)
    
    def get_user_context_count(self) -> int:
        """
        获取用户上下文数量
        
        Returns:
            int: 用户上下文数量
        """
        return len(self._user_contexts)
    
    def __repr__(self) -> str:
        """返回对象的字符串表示"""
        return f"ContextManager(flow_contexts={len(self._flow_contexts)}, user_contexts={len(self._user_contexts)})"


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

