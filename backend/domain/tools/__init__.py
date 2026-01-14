"""
工具系统
"""
import logging
from backend.domain.tools.registry import ToolRegistry, tool_registry
from backend.domain.tools.context import (
    RuntimeContext,
    get_token_id,
    set_token_id,
    get_session_id,
    set_session_id,
    get_trace_id,
    set_trace_id
)
# 导入工具注册装饰器
from backend.domain.tools.decorator import register_tool

logger = logging.getLogger(__name__)


# 初始化工具注册表（自动注册所有工具）
def init_tools():
    """
    初始化工具注册表
    
    注意：工具现在通过 @register_tool 装饰器自动注册，
    此函数只需要导入工具模块即可触发注册。
    
    导入顺序：
    1. 导入所有工具模块
    2. 模块加载时，@register_tool 装饰器自动执行注册
    """
    # 导入工具模块（触发自动注册）
    # 注意：导入顺序很重要，确保所有工具模块都被导入
    from backend.domain.tools import blood_pressure  # noqa: F401
    
    # 可以在这里导入更多工具模块
    # from backend.domain.tools import appointment  # noqa: F401
    # from backend.domain.tools import medication  # noqa: F401
    
    # 获取已注册的工具数量
    registered_tools = tool_registry.get_all_tools()
    logger.info(f"工具注册表初始化完成，共注册 {len(registered_tools)} 个工具")


__all__ = [
    "ToolRegistry",
    "tool_registry",
    "RuntimeContext",
    "get_token_id",
    "set_token_id",
    "get_session_id",
    "set_session_id",
    "get_trace_id",
    "set_trace_id",
    "register_tool",  # 导出装饰器，供工具定义使用
    "init_tools",
]
