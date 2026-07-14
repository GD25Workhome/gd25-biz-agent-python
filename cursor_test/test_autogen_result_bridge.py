"""
AutoGen 结果桥测试
"""
from __future__ import annotations

from types import SimpleNamespace

from backend.domain.autogen.result_bridge import (
    extract_final_content_and_approved,
    failure_flow_patch,
    to_flow_patch,
)
from backend.domain.flows.models.autogen_config import (
    AutogenAgentSpec,
    AutogenOutputConfig,
    AutogenTeamNodeConfig,
    AutogenTerminationConfig,
)
from backend.domain.flows.models.definition import ModelConfig


def _msg(source: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(source=source, content=content, type="TextMessage")


def _config(**overrides) -> AutogenTeamNodeConfig:
    base = {
        "team_mode": "round_robin",
        "model": ModelConfig(provider="doubao", name="m", temperature=0.3),
        "agents": [
            AutogenAgentSpec(name="writer", system_prompt="prompts/writer.md"),
            AutogenAgentSpec(name="critic", system_prompt="prompts/critic.md"),
        ],
        "termination": AutogenTerminationConfig(text_mention="APPROVE", max_messages=8),
        "output": AutogenOutputConfig(
            write_to_flow_msgs=True,
            edges_var_key="review_approved",
            persist_transcript=False,
            content_max_chars=8000,
        ),
    }
    base.update(overrides)
    return AutogenTeamNodeConfig(**base)


def test_extract_approved_with_writer_content() -> None:
    """APPROVE 后向前取 writer 正文。"""
    messages = [
        _msg("user", "写一首短诗"),
        _msg("writer", "秋叶飘落"),
        _msg("critic", "请更生动"),
        _msg("writer", "金秋落叶舞清风"),
        _msg("critic", "APPROVE"),
    ]
    content, approved = extract_final_content_and_approved(messages, "APPROVE", 8000)
    assert approved is True
    assert content == "金秋落叶舞清风"


def test_extract_not_approved() -> None:
    """无 APPROVE 时 approved=False，仍取最后有效正文。"""
    messages = [
        _msg("user", "任务"),
        _msg("writer", "草稿一"),
        _msg("critic", "再改"),
        _msg("writer", "草稿二"),
    ]
    content, approved = extract_final_content_and_approved(messages, "APPROVE", 8000)
    assert approved is False
    assert content == "草稿二"


def test_to_flow_patch_approve_path() -> None:
    """成功批准路径写入 team_result / edges_var / flow_msgs。"""
    result = SimpleNamespace(
        messages=[
            _msg("user", "任务"),
            _msg("writer", "终稿"),
            _msg("critic", "APPROVE"),
        ],
        stop_reason="Text 'APPROVE' mentioned",
    )
    patch = to_flow_patch(result, _config(), state={})
    assert patch["team_result"]["approved"] is True
    assert patch["team_result"]["final_content"] == "终稿"
    assert patch["edges_var"]["review_approved"] is True
    assert patch["edges_var"]["team_finished"] is True
    assert patch["flow_msgs"][0].content == "终稿"


def test_to_flow_patch_with_transcript() -> None:
    """persist_transcript=True 时应写入 team_transcript。"""
    cfg = _config(
        output=AutogenOutputConfig(
            write_to_flow_msgs=True,
            edges_var_key="review_approved",
            persist_transcript=True,
            max_transcript_messages=10,
            content_max_chars=8000,
        )
    )
    result = SimpleNamespace(
        messages=[_msg("user", "u"), _msg("writer", "w")],
        stop_reason="Maximum number of messages reached",
    )
    patch = to_flow_patch(result, cfg, state={})
    assert "team_transcript" in patch
    assert patch["team_result"]["hit_max_messages"] is True
    assert patch["team_result"]["approved"] is False


def test_failure_flow_patch_timeout() -> None:
    """超时补丁字段齐全。"""
    patch = failure_flow_patch(
        _config(),
        {},
        user_message="评审协作超时，请稍后重试或缩短任务描述。",
        stop_reason="timeout",
        error="timeout after 1s",
        timed_out=True,
    )
    assert patch["team_result"]["timed_out"] is True
    assert patch["team_result"]["approved"] is False
    assert patch["edges_var"]["team_stop_reason"] == "timeout"
    assert "超时" in patch["flow_msgs"][0].content
