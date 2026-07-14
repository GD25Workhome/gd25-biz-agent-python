"""
AutogenTeamNodeCreator 与形态 A flow 解析测试
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition
from backend.domain.flows.nodes.autogen_team_creator import AutogenTeamNodeCreator
from backend.domain.flows.nodes.registry import node_creator_registry
from backend.domain.flows.parser import FlowParser


def _minimal_node_config(**overrides) -> dict:
    cfg = {
        "team_mode": "round_robin",
        "model": {"provider": "doubao", "name": "doubao-test", "temperature": 0.3},
        "agents": [
            {"name": "writer", "system_prompt": "prompts/writer.md", "tools": []},
            {"name": "critic", "system_prompt": "prompts/critic.md", "tools": []},
        ],
        "termination": {"text_mention": "APPROVE", "max_messages": 8},
        "timeout_seconds": 120,
        "output": {
            "write_to_flow_msgs": True,
            "edges_var_key": "review_approved",
            "persist_transcript": False,
            "content_max_chars": 8000,
        },
    }
    cfg.update(overrides)
    return cfg


@pytest.mark.asyncio
async def test_node_success_with_mocked_team() -> None:
    """mock team.run 成功路径应产出 flow_msgs 与 team_result。"""
    flow_dir = str(
        Path(__file__).resolve().parents[1]
        / "config"
        / "flows"
        / "autogen_review_agent"
    )
    node_def = NodeDefinition(name="review_team", type="autogen_team", config=_minimal_node_config())
    flow_def = FlowDefinition(
        name="autogen_review_agent",
        version="1.0",
        nodes=[node_def],
        edges=[],
        entry_node="review_team",
        flow_dir=flow_dir,
    )
    creator = AutogenTeamNodeCreator()
    node_fn = creator.create(node_def, flow_def)

    fake_result = SimpleNamespace(
        messages=[
            SimpleNamespace(source="user", content="写短建议", type="TextMessage"),
            SimpleNamespace(source="writer", content="多喝水少熬夜", type="TextMessage"),
            SimpleNamespace(source="critic", content="APPROVE", type="TextMessage"),
        ],
        stop_reason="Text 'APPROVE' mentioned",
    )

    fake_team = MagicMock()
    fake_team.run = AsyncMock(return_value=fake_result)
    fake_team.reset = AsyncMock()

    with (
        patch(
            "backend.domain.flows.nodes.autogen_team_creator.get_autogen_model_client",
            return_value=MagicMock(),
        ),
        patch(
            "backend.domain.flows.nodes.autogen_team_creator.AssistantAgent",
            side_effect=lambda **kwargs: MagicMock(name=kwargs["name"]),
        ),
        patch(
            "backend.domain.flows.nodes.autogen_team_creator.RoundRobinGroupChat",
            return_value=fake_team,
        ),
        patch(
            "backend.domain.flows.nodes.autogen_team_creator.prompt_manager.cached_prompt",
            return_value="prompt-cache-key",
        ),
        patch(
            "backend.domain.flows.nodes.autogen_team_creator.build_system_message",
            return_value=SimpleNamespace(content="system"),
        ),
    ):
        state = {"current_message": HumanMessage(content="写短建议"), "token_id": "t1"}
        patch_out = await node_fn(state)

    assert patch_out["team_result"]["approved"] is True
    assert patch_out["team_result"]["final_content"] == "多喝水少熬夜"
    assert patch_out["flow_msgs"][0].content == "多喝水少熬夜"
    assert patch_out["edges_var"]["review_approved"] is True
    fake_team.reset.assert_awaited()


@pytest.mark.asyncio
async def test_node_timeout_path() -> None:
    """超时应返回固定用户文案与 timed_out=True。"""
    flow_dir = str(
        Path(__file__).resolve().parents[1]
        / "config"
        / "flows"
        / "autogen_review_agent"
    )
    node_def = NodeDefinition(
        name="review_team",
        type="autogen_team",
        config=_minimal_node_config(timeout_seconds=120),
    )
    flow_def = FlowDefinition(
        name="autogen_review_agent",
        version="1.0",
        nodes=[node_def],
        edges=[],
        entry_node="review_team",
        flow_dir=flow_dir,
    )
    node_fn = AutogenTeamNodeCreator().create(node_def, flow_def)

    fake_team = MagicMock()
    fake_team.run = AsyncMock(return_value=SimpleNamespace(messages=[], stop_reason=None))
    fake_team.reset = AsyncMock()

    async def _raise_timeout(*_args, **_kwargs):
        raise TimeoutError()

    with (
        patch(
            "backend.domain.flows.nodes.autogen_team_creator.get_autogen_model_client",
            return_value=MagicMock(),
        ),
        patch(
            "backend.domain.flows.nodes.autogen_team_creator.AssistantAgent",
            return_value=MagicMock(),
        ),
        patch(
            "backend.domain.flows.nodes.autogen_team_creator.RoundRobinGroupChat",
            return_value=fake_team,
        ),
        patch(
            "backend.domain.flows.nodes.autogen_team_creator.prompt_manager.cached_prompt",
            return_value="prompt-cache-key",
        ),
        patch(
            "backend.domain.flows.nodes.autogen_team_creator.build_system_message",
            return_value=SimpleNamespace(content="system"),
        ),
        patch(
            "backend.domain.flows.nodes.autogen_team_creator.asyncio.wait_for",
            side_effect=_raise_timeout,
        ),
    ):
        patch_out = await node_fn({"current_message": HumanMessage(content="hi")})

    assert patch_out["team_result"]["timed_out"] is True
    assert patch_out["team_result"]["approved"] is False
    assert "超时" in patch_out["flow_msgs"][0].content
    fake_team.reset.assert_awaited()


def test_unsupported_team_mode_raises() -> None:
    """selector 模式首期应拒绝。"""
    node_def = NodeDefinition(
        name="review_team",
        type="autogen_team",
        config=_minimal_node_config(team_mode="selector"),
    )
    flow_def = FlowDefinition(
        name="t",
        version="1.0",
        nodes=[node_def],
        edges=[],
        entry_node="review_team",
        flow_dir="/tmp",
    )
    with pytest.raises(ValueError, match="首期仅支持"):
        AutogenTeamNodeCreator().create(node_def, flow_def)


def test_parse_autogen_review_agent_flow() -> None:
    """形态 A flow.yaml 可被解析且节点类型已注册。"""
    yaml_path = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "flows"
        / "autogen_review_agent"
        / "flow.yaml"
    )
    flow_def = FlowParser.parse_yaml(yaml_path)
    assert flow_def.name == "autogen_review_agent"
    assert flow_def.entry_node == "review_team"
    assert flow_def.nodes[0].type == "autogen_team"
    assert "autogen_team" in node_creator_registry.get_all_types()


def test_build_graph_for_autogen_review_agent() -> None:
    """形态 A 流程图应可编译（不执行 LLM）。"""
    from backend.domain.flows.builder import GraphBuilder

    yaml_path = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "flows"
        / "autogen_review_agent"
        / "flow.yaml"
    )
    flow_def = FlowParser.parse_yaml(yaml_path)
    graph = GraphBuilder.build_graph(flow_def)
    assert graph is not None
