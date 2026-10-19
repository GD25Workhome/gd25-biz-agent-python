"""
工具系统
华院最小部署：仅注册文档工具、AnySearch、博查。
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
        初始化工具注册表（仅华院相关工具）。

        通过导入工具模块触发 @register_tool 自动注册。
    """
    # 1. 导入华院工具模块（触发自动注册）
    from backend.domain.tools import huayuan_document_tool  # noqa: F401
    # 规则二知识库：按 doc_id 拉新闻正文（白名单=本次召回 doc_ids，受 max_load_times 限制）
    from backend.domain.tools import load_news_document_tool  # noqa: F401
    # AnySearch：默认走「DB 凭证池」的新实现（anysearch_flow）；
    # ANYSEARCH_TOOL_IMPL=legacy 可回退旧的 env 实现（anysearch_tool）。
    import os as _os

    if _os.getenv("ANYSEARCH_TOOL_IMPL", "new").strip().lower() == "legacy":
        from backend.domain.tools import anysearch_tool  # noqa: F401
    else:
        from backend.domain.tools import anysearch_flow  # noqa: F401
    from backend.domain.tools import bocha_tool  # noqa: F401
    # DeepSeek 网页搜索 / 抓取：独立工具（不依赖华院 radar 上下文），供规则二 v3 检索链路
    from backend.domain.tools import deepseek_search_tool  # noqa: F401
    # 区域字典查询：供规则二 v3 Agent 确定「展厅所在区域」（只读 region/region_alias）
    from backend.domain.tools import region_lookup_tool  # noqa: F401

    # 2. 打印已注册数量，便于启动日志核对
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
