"""
Function节点基类
所有Function节点必须继承此基类
"""
from abc import ABC, abstractmethod

from backend.domain.state import FlowState


class BaseFunctionNode(ABC):
    """Function节点基类"""
    
    def __init_subclass__(cls, **kwargs):
        """
        子类定义时自动注册到注册表
        
        当任何继承BaseFunctionNode的类被定义时，会自动调用此方法进行注册。
        这样就不需要手动扫描目录或手动注册了。
        """
        super().__init_subclass__(**kwargs)
        
        # 自动注册子类（排除基类本身）
        if cls != BaseFunctionNode:
            # 延迟导入注册表，避免循环依赖
            # 使用函数内导入，确保注册表已创建
            try:
                from backend.domain.flows.nodes.function_registry import function_registry
                key = cls.get_key()
                if key:
                    function_registry.register(cls)
            except Exception as e:
                # 如果get_key()还未实现或出错，记录警告但不中断
                # 这种情况可能发生在类定义过程中，get_key()可能还未完全定义
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(
                    f"自动注册Function节点 {cls.__name__} 时出错（可能类还未完全定义）: {e}。"
                    f"节点将在discover()时重新尝试注册。"
                )
    
    @abstractmethod
    async def execute(self, state: FlowState) -> FlowState:
        """
        执行节点逻辑（异步）
        
        Args:
            state: 流程状态对象
            
        Returns:
            FlowState: 更新后的状态对象
        """
        pass
    
    @classmethod
    @abstractmethod
    def get_key(cls) -> str:
        """
        返回节点的唯一标识key
        
        Returns:
            str: 节点的唯一标识，用于在配置中引用
        """
        pass
