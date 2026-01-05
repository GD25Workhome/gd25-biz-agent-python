"""
流程上下文：流程级别的共享数据
用于Agent间数据传递和提示词占位符替换
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class FlowContext:
    """
    流程上下文：流程级别的共享数据
    
    用于存储流程执行过程中的中间结果和共享数据，
    支持Agent间数据传递和提示词占位符替换。
    """
    
    def __init__(self):
        """
        初始化流程上下文
        """
        self._data: Dict[str, Any] = {}
        logger.debug("创建FlowContext实例")
    
    def set(self, key: str, value: Any) -> None:
        """
        设置数据
        
        Args:
            key: 数据键
            value: 数据值
        """
        self._data[key] = value
        logger.debug(f"FlowContext设置数据: key={key}, value_type={type(value).__name__}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取数据
        
        Args:
            key: 数据键
            default: 默认值（如果键不存在）
            
        Returns:
            数据值，如果键不存在则返回默认值
        """
        value = self._data.get(key, default)
        logger.debug(f"FlowContext获取数据: key={key}, found={key in self._data}")
        return value
    
    def update(self, data: Dict[str, Any]) -> None:
        """
        批量更新数据
        
        Args:
            data: 要更新的数据字典
        """
        self._data.update(data)
        logger.debug(f"FlowContext批量更新数据: keys={list(data.keys())}")
    
    def clear(self) -> None:
        """
        清空所有数据
        """
        self._data.clear()
        logger.debug("FlowContext清空所有数据")
    
    def remove(self, key: str) -> Any:
        """
        移除指定键的数据
        
        Args:
            key: 要移除的数据键
            
        Returns:
            被移除的数据值，如果键不存在则返回None
        """
        value = self._data.pop(key, None)
        if value is not None:
            logger.debug(f"FlowContext移除数据: key={key}")
        return value
    
    def has(self, key: str) -> bool:
        """
        检查指定键是否存在
        
        Args:
            key: 数据键
            
        Returns:
            如果键存在返回True，否则返回False
        """
        return key in self._data
    
    @property
    def data(self) -> Dict[str, Any]:
        """
        获取所有数据的副本
        
        Returns:
            所有数据的字典副本
        """
        return self._data.copy()
    
    def __repr__(self) -> str:
        """返回对象的字符串表示"""
        return f"FlowContext(keys={list(self._data.keys())})"

