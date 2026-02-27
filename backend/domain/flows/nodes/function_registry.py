"""
Function节点注册表
使用Python的__subclasses__机制自动发现所有Function节点
"""
import logging
from typing import Dict, Type, Optional, Set

from backend.domain.flows.nodes.base_function import BaseFunctionNode

logger = logging.getLogger(__name__)


class FunctionRegistry:
    """Function节点注册表（单例模式）"""
    
    _instance: 'FunctionRegistry' = None
    _nodes: Dict[str, Type[BaseFunctionNode]] = {}
    _discovered: bool = False
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, node_class: Type[BaseFunctionNode]) -> None:
        """
        注册Function节点类
        
        Args:
            node_class: Function节点类（必须继承BaseFunctionNode）
            
        Raises:
            ValueError: 如果节点类无效或key已存在
        """
        if not issubclass(node_class, BaseFunctionNode):
            raise ValueError(f"节点类 {node_class.__name__} 必须继承 BaseFunctionNode")
        
        key = node_class.get_key()
        if not key:
            raise ValueError(f"节点类 {node_class.__name__} 的 get_key() 方法返回了空值")
        
        if key in self._nodes:
            existing_class = self._nodes[key]
            if existing_class != node_class:
                logger.warning(
                    f"Function节点 key '{key}' 已存在，将被覆盖。"
                    f"原类: {existing_class.__name__}, 新类: {node_class.__name__}"
                )
        
        self._nodes[key] = node_class
        logger.debug(f"注册Function节点: {key} -> {node_class.__name__}")
    
    def get(self, key: str) -> Optional[Type[BaseFunctionNode]]:
        """
        根据key获取Function节点类
        
        如果节点未找到，会尝试发现所有子类（懒加载）
        
        Args:
            key: 节点key
            
        Returns:
            Type[BaseFunctionNode]: 节点类，如果不存在则返回None
        """
        # 如果节点未找到且还未发现过，尝试发现所有子类
        if key not in self._nodes and not self._discovered:
            self.discover()
        
        return self._nodes.get(key)
    
    def get_all_keys(self) -> list:
        """
        获取所有已注册的节点key
        
        Returns:
            list: 节点key列表
        """
        # 确保已发现所有子类
        if not self._discovered:
            self.discover()
        
        return list(self._nodes.keys())
    
    def discover(self) -> None:
        """
        发现所有BaseFunctionNode的子类并注册
        
        使用Python的__subclasses__()机制递归查找所有子类。
        这比扫描目录更优雅，因为：
        1. 不依赖目录结构
        2. 自动发现所有已导入的子类
        3. 支持子类在任何位置定义
        
        注意：此方法只会发现已经导入的模块中的子类。
        如果需要发现未导入的模块，需要先导入相关模块。
        """
        if self._discovered:
            return
        
        try:
            # 递归获取所有子类（包括间接子类）
            all_subclasses = self._get_all_subclasses(BaseFunctionNode)
            
            # 注册所有子类
            for subclass in all_subclasses:
                try:
                    # 检查是否已经注册（避免重复）
                    key = subclass.get_key()
                    if key and key not in self._nodes:
                        self.register(subclass)
                        logger.info(f"发现并注册Function节点: {key} -> {subclass.__name__}")
                except Exception as e:
                    logger.warning(
                        f"注册Function节点 {subclass.__name__} 时出错: {e}。"
                        f"请确保类已正确定义 get_key() 方法。"
                    )
        
        except Exception as e:
            logger.error(f"发现Function节点时出错: {e}", exc_info=True)
        finally:
            self._discovered = True
            logger.info(f"Function节点发现完成，共注册 {len(self._nodes)} 个节点")
    
    @staticmethod
    def _get_all_subclasses(cls: Type) -> Set[Type]:
        """
        递归获取所有子类（包括间接子类）
        
        Args:
            cls: 基类
            
        Returns:
            Set[Type]: 所有子类的集合
        """
        subclasses = set(cls.__subclasses__())
        for subclass in list(subclasses):
            # 递归获取子类的子类
            subclasses.update(FunctionRegistry._get_all_subclasses(subclass))
        return subclasses


# 创建全局注册表实例
function_registry = FunctionRegistry()
