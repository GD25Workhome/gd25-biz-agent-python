"""
工具注册装饰器
提供 @register_tool 装饰器，自动注册工具到工具注册表
"""
import logging
from langchain_core.tools import tool
from backend.domain.tools.registry import tool_registry

logger = logging.getLogger(__name__)


def register_tool(func=None, *, auto_register=True):
    """
    工具注册装饰器
    
    用法1（推荐）：
        @register_tool
        async def my_tool(...):
            ...
    
    用法2（带参数）：
        @register_tool(auto_register=True)
        async def my_tool(...):
            ...
    
    用法3（不自动注册）：
        @register_tool(auto_register=False)
        async def my_tool(...):
            ...
    
    Args:
        func: 被装饰的函数（当作为装饰器使用时为 None）
        auto_register: 是否自动注册到工具注册表（默认 True）
    
    Returns:
        装饰后的工具函数（BaseTool 实例）
    """
    def decorator(f):
        # 先使用 @tool 装饰器，将函数转换为 BaseTool 实例
        tool_func = tool(f)
        
        # 自动注册到工具注册表
        if auto_register:
            tool_name = getattr(tool_func, 'name', None)
            
            # 检查是否已注册（防止重复注册）
            existing_tool = tool_registry.get_tool(tool_name) if tool_name else None
            if existing_tool is None:
                tool_registry.register(tool_func)
                logger.info(f"自动注册工具: {tool_name}")
            else:
                logger.debug(f"工具 {tool_name} 已注册，跳过重复注册")
        
        return tool_func
    
    # 支持两种用法：@register_tool 和 @register_tool(auto_register=True)
    if func is None:
        # 用法2：@register_tool(auto_register=True)
        return decorator
    else:
        # 用法1：@register_tool
        return decorator(func)

