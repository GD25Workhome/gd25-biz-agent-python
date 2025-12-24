"""
加载器注册表
管理所有数据加载器，提供统一的加载器获取接口
"""
from typing import Dict, Optional
import logging

from .data_loaders import DataLoader

logger = logging.getLogger(__name__)

# 延迟导入LangfuseLoader，避免在未安装时出错
try:
    from .langfuse_loader import LangfuseLoader
    LANGFUSE_LOADER_AVAILABLE = True
except (ImportError, ValueError):
    LANGFUSE_LOADER_AVAILABLE = False


class LoaderRegistry:
    """加载器注册表"""
    
    _loaders: Dict[str, DataLoader] = {}
    _initialized = False
    
    @classmethod
    def _initialize(cls):
        """初始化默认加载器"""
        if cls._initialized:
            return
        
        # 注册默认加载器（注意顺序，更具体的加载器应该先注册）
        # 顺序很重要：更具体的匹配应该在前
        
        # 只注册Langfuse加载器（唯一数据源）
        if LANGFUSE_LOADER_AVAILABLE:
            try:
                langfuse_loader = LangfuseLoader()
                cls.register("langfuse", langfuse_loader)
                logger.debug("已注册Langfuse加载器")
            except Exception as e:
                logger.error(f"注册Langfuse加载器失败: {e}")
                raise ValueError(f"无法注册Langfuse加载器: {e}")
        else:
            raise ValueError("Langfuse加载器不可用，请检查Langfuse配置")
        
        cls._initialized = True
        logger.debug("加载器注册表已初始化")
    
    @classmethod
    def register(cls, name: str, loader: DataLoader):
        """
        注册加载器
        
        Args:
            name: 加载器名称
            loader: 加载器实例
        """
        cls._loaders[name] = loader
        logger.debug(f"注册加载器: {name}")
    
    @classmethod
    def get_loader(cls, source: str) -> Optional[DataLoader]:
        """
        根据数据源获取合适的加载器
        
        Args:
            source: 数据源字符串
        
        Returns:
            合适的加载器实例，如果找不到则返回None
        """
        cls._initialize()
        
        # 按注册顺序检查每个加载器是否支持该数据源
        # 注意：更具体的加载器应该先注册
        for name, loader in cls._loaders.items():
            if loader.supports(source):
                logger.debug(f"为数据源 {source} 找到加载器: {name} ({type(loader).__name__})")
                return loader
        
        logger.warning(f"未找到支持数据源 {source} 的加载器")
        return None
    
    @classmethod
    def get_loader_by_name(cls, name: str) -> Optional[DataLoader]:
        """
        根据名称获取加载器
        
        Args:
            name: 加载器名称
        
        Returns:
            加载器实例，如果不存在则返回None
        """
        cls._initialize()
        return cls._loaders.get(name)
