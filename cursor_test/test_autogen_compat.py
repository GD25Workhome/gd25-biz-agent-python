"""
AutoGen 包兼容性检查（P0）
"""
from __future__ import annotations

import importlib.metadata as metadata


def test_autogen_packages_installed() -> None:
    """autogen 相关包版本应满足 >=0.7。"""
    for pkg in ("autogen-agentchat", "autogen-core", "autogen-ext"):
        version = metadata.version(pkg)
        major_minor = tuple(int(x) for x in version.split(".")[:2])
        assert major_minor >= (0, 7), f"{pkg}={version} 过低"


def test_autogen_and_langgraph_importable() -> None:
    """AutoGen Team 与 langgraph 可同进程 import。"""
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.teams import RoundRobinGroupChat, SelectorGroupChat
    from autogen_ext.models.openai import OpenAIChatCompletionClient
    import langgraph  # noqa: F401
    import langchain  # noqa: F401

    assert AssistantAgent is not None
    assert RoundRobinGroupChat is not None
    assert SelectorGroupChat is not None
    assert OpenAIChatCompletionClient is not None


def test_autogen_team_registered() -> None:
    """节点注册表应包含 autogen_team。"""
    from backend.domain.flows.nodes.registry import node_creator_registry

    assert "autogen_team" in node_creator_registry.get_all_types()
