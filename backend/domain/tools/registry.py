"""
工具注册表
管理所有可用的工具
"""
import logging
from typing import Dict, Optional
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表（单例模式）"""
    
    _instance: 'ToolRegistry' = None
    _tools: Dict[str, BaseTool] = {}
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, tool: BaseTool) -> None:
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        self._tools[tool.name] = tool
        logger.info(f"注册工具: {tool.name}")
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        获取工具
        
        Args:
            name: 工具名称
            
        Returns:
            工具实例，如果不存在则返回None
        """
        return self._tools.get(name)
    
    def get_all_tools(self) -> Dict[str, BaseTool]:
        """
        获取所有工具
        
        Returns:
            所有工具的字典
        """
        return self._tools.copy()
    
    def clear(self) -> None:
        """清空所有工具"""
        self._tools.clear()


# 创建全局工具注册表实例
tool_registry = ToolRegistry()

