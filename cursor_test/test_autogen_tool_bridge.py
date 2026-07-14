"""
AutoGen 工具桥测试
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.domain.autogen.tool_bridge import wrap_registry_tools


@pytest.mark.asyncio
async def test_wrap_unknown_tool_raises() -> None:
    """未注册工具名应立即报错。"""
    with patch(
        "backend.domain.autogen.tool_bridge.tool_registry.get_tool",
        return_value=None,
    ):
        with pytest.raises(ValueError, match="工具未注册"):
            wrap_registry_tools(["no_such_tool"])


@pytest.mark.asyncio
async def test_wrap_tool_truncates_long_result() -> None:
    """超长返回应截断并带 truncated 标记。"""
    fake_tool = MagicMock()
    fake_tool.name = "fake_tool"
    fake_tool.description = "假工具"
    fake_tool.args_schema = None

    async def _ainvoke(_kwargs):
        return "x" * 100

    fake_tool.ainvoke = _ainvoke

    with patch(
        "backend.domain.autogen.tool_bridge.tool_registry.get_tool",
        return_value=fake_tool,
    ):
        tools = wrap_registry_tools(["fake_tool"], result_max_chars=20)
        assert len(tools) == 1
        result = await tools[0](foo=1)
        assert result.endswith("...(truncated)")
        assert len(result) == 20 + len("...(truncated)")


@pytest.mark.asyncio
async def test_wrap_tool_exception_becomes_tool_error() -> None:
    """工具异常应转为 TOOL_ERROR 字符串。"""
    fake_tool = MagicMock()
    fake_tool.name = "boom"
    fake_tool.description = "会炸"
    fake_tool.args_schema = None

    async def _ainvoke(_kwargs):
        raise RuntimeError("boom")

    fake_tool.ainvoke = _ainvoke

    with patch(
        "backend.domain.autogen.tool_bridge.tool_registry.get_tool",
        return_value=fake_tool,
    ):
        tools = wrap_registry_tools(["boom"])
        result = await tools[0]()
        assert result.startswith("TOOL_ERROR: boom:")
