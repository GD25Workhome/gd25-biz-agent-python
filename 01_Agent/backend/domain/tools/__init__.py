"""
工具系统
"""
from backend.domain.tools.registry import ToolRegistry, tool_registry
from backend.domain.tools.blood_pressure import record_blood_pressure


# 初始化工具注册表（注册所有工具）
def init_tools():
    """初始化工具注册表"""
    tool_registry.register(record_blood_pressure)


# 自动初始化
init_tools()
