"""
工具系统（规则二最小集）

仅注册规则二 v3 使用的工具：
- DeepSeek 网页搜索 / 抓取
- 区域字典查询
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
    set_trace_id,
)
from backend.domain.tools.decorator import register_tool

logger = logging.getLogger(__name__)


def init_tools() -> None:
    """
        初始化工具注册表（规则二最小集）。

        通过导入工具模块触发 @register_tool 自动注册。
    """
    # 1. 规则二 v3 检索链：DeepSeek Search / Fetch
    from backend.domain.tools import deepseek_search_tool  # noqa: F401
    # 2. 区域字典：确定「展厅所在区域」
    from backend.domain.tools import region_lookup_tool  # noqa: F401
    # 3. AnySearch（DB 凭证池版）：恢复为可用工具；当前未挂进 v3 flow，仅注册
    from backend.domain.tools import anysearch_flow  # noqa: F401

    # 4. 打印已注册数量，便于启动日志核对
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
    "register_tool",
    "init_tools",
]
