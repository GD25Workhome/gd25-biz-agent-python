"""
AutoGen 工具桥

将 tool_registry 中的 LangChain Tool 包装为 AutoGen AssistantAgent 可调用函数。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, List, Optional

from backend.domain.tools.registry import tool_registry

logger = logging.getLogger(__name__)


def _truncate_result(value: Any, max_chars: int) -> str:
    """将工具返回值转为字符串并按上限截断。"""
    text = value if isinstance(value, str) else str(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...(truncated)"


def wrap_registry_tools(
    tool_names: List[str],
    *,
    token_id: Optional[str] = None,
    result_max_chars: int = 4000,
) -> List[Callable[..., Any]]:
    """
        将 tool_registry 中的工具包装为 AutoGen 可调用函数。

        仅暴露 YAML 点名的工具；未知工具名立即失败。异常转为 TOOL_ERROR 字符串，
        避免打垮 Team。token_id 参数保留供将来显式注入；现网工具多依赖 RuntimeContext。

        Args:
            tool_names: 工具名列表
            token_id: 会话令牌（文档化保留；主路径由 chat RuntimeContext 注入）
            result_max_chars: 返回文本截断上限

        Returns:
            可供 AssistantAgent(tools=...) 使用的可调用列表

        Raises:
            ValueError: 工具未在 registry 中注册
    """
    _ = token_id  # 现网工具读 contextvars；保留参数以对齐技术设计签名
    wrapped: List[Callable[..., Any]] = []

    for name in tool_names:
        # 1. 从注册表查找工具
        tool = tool_registry.get_tool(name)
        if tool is None:
            raise ValueError(f"工具未注册: {name}")

        # 2. 包装为具名 async 函数（保留工具元数据便于 AutoGen 推断 schema）
        wrapped.append(_make_tool_wrapper(tool, name, result_max_chars))

    return wrapped


def _make_tool_wrapper(
    tool: Any,
    tool_name: str,
    result_max_chars: int,
) -> Callable[..., Any]:
    """
        为单个 BaseTool 创建包装协程。

        Args:
            tool: LangChain BaseTool 实例
            tool_name: 工具名（用于错误文案）
            result_max_chars: 截断上限

        Returns:
            async 可调用对象
    """

    async def _wrapped(**kwargs: Any) -> str:
        """
            调用底层 LangChain 工具并返回截断后的字符串。

            Args:
                **kwargs: 工具入参

            Returns:
                成功结果或 TOOL_ERROR 前缀字符串
        """
        try:
            # 优先 ainvoke；同步 invoke 放到线程池
            if hasattr(tool, "ainvoke"):
                raw = await tool.ainvoke(kwargs)
            elif hasattr(tool, "invoke"):
                raw = await asyncio.to_thread(tool.invoke, kwargs)
            elif callable(tool):
                result = tool(**kwargs)
                if asyncio.iscoroutine(result):
                    raw = await result
                else:
                    raw = await asyncio.to_thread(lambda: result)
            else:
                return f"TOOL_ERROR: {tool_name}: 工具不可调用"
            return _truncate_result(raw, result_max_chars)
        except Exception as exc:  # noqa: BLE001 - 需吞掉异常保护 Team
            logger.warning("AutoGen 工具调用失败 name=%s err=%s", tool_name, exc, exc_info=True)
            return f"TOOL_ERROR: {tool_name}: {exc}"

    _wrapped.__name__ = tool_name
    _wrapped.__doc__ = getattr(tool, "description", None) or f"工具: {tool_name}"
    # 尽量透传 args schema，供 AutoGen 生成 function calling 定义
    if hasattr(tool, "args_schema") and tool.args_schema is not None:
        _wrapped.__annotations__ = getattr(tool.args_schema, "__annotations__", {})
    return _wrapped
