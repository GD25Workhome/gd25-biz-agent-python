"""
工具系统
"""
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
# TokenInjectedTool 已废弃：工具内部已使用 get_token_id() 获取 token_id，不再需要包装器
# from backend.domain.tools.wrapper import TokenInjectedTool, wrap_tools_with_token_context
from backend.domain.tools.blood_pressure import record_blood_pressure


# 初始化工具注册表（注册所有工具）
def init_tools():
    """
    初始化工具注册表
    
    导入并注册所有业务工具
    """
    # 注册血压记录工具
    tool_registry.register(record_blood_pressure)
    
    # 可以在这里注册更多工具
    # from backend.domain.tools.xxx import xxx_tool
    # tool_registry.register(xxx_tool)


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
    # TokenInjectedTool 已废弃：工具内部已使用 get_token_id() 获取 token_id
    # "TokenInjectedTool",
    # "wrap_tools_with_token_context",
    "init_tools",
]
