"""
验证 Claude Agent SDK 凭证与本机 shell / ~/.claude 隔离。
"""
from __future__ import annotations

from pathlib import Path

from backend.app.config import (
    ANTHROPIC_SDK_DEFAULTS,
    Settings,
    build_claude_sdk_env,
    resolve_anthropic_sdk_value,
)


def test_resolve_ignores_shell_when_dotenv_exists(
    tmp_path: Path,
) -> None:
    """
        有项目 .env 时：即使 settings_fallback 带「本机个人 key」，也不采用。
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ANTHROPIC_AUTH_TOKEN=project-token\n",
        encoding="utf-8",
    )
    dotenv_map = {"ANTHROPIC_AUTH_TOKEN": "project-token"}

    assert (
        resolve_anthropic_sdk_value(
            "ANTHROPIC_AUTH_TOKEN",
            "personal-shell-token",
            project_dotenv=dotenv_map,
            env_file=env_file,
        )
        == "project-token"
    )
    # .env 未写 API_KEY → 不得回落 shell
    assert (
        resolve_anthropic_sdk_value(
            "ANTHROPIC_API_KEY",
            "personal-api-key",
            project_dotenv=dotenv_map,
            env_file=env_file,
        )
        is None
    )


def test_resolve_uses_defaults_for_base_url_and_model(
    tmp_path: Path,
) -> None:
    """未写 BASE_URL / MODEL 时回落项目默认值。"""
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_AUTH_TOKEN=t\n", encoding="utf-8")
    dotenv_map = {"ANTHROPIC_AUTH_TOKEN": "t"}

    assert (
        resolve_anthropic_sdk_value(
            "ANTHROPIC_BASE_URL",
            None,
            project_dotenv=dotenv_map,
            env_file=env_file,
        )
        == ANTHROPIC_SDK_DEFAULTS["ANTHROPIC_BASE_URL"]
    )
    assert (
        resolve_anthropic_sdk_value(
            "ANTHROPIC_MODEL",
            None,
            project_dotenv=dotenv_map,
            env_file=env_file,
        )
        == ANTHROPIC_SDK_DEFAULTS["ANTHROPIC_MODEL"]
    )


def test_resolve_without_dotenv_uses_settings_fallback(
    tmp_path: Path,
) -> None:
    """无 .env（K8s）时允许 Settings / 进程环境回退。"""
    missing = tmp_path / "no-such.env"
    assert not missing.exists()
    assert (
        resolve_anthropic_sdk_value(
            "ANTHROPIC_AUTH_TOKEN",
            "k8s-secret-token",
            project_dotenv={},
            env_file=missing,
        )
        == "k8s-secret-token"
    )


def test_build_claude_sdk_env_blanks_and_isolates_config_dir(
    tmp_path: Path,
) -> None:
    """
        组装结果：项目 token 生效、未配置键为空串、CLAUDE_CONFIG_DIR 落在项目内。
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ANTHROPIC_AUTH_TOKEN=project-token\n",
        encoding="utf-8",
    )
    settings_obj = Settings(
        _env_file=None,  # type: ignore[call-arg]
        ENABLE_DATABASE=False,
        ANTHROPIC_AUTH_TOKEN="should-not-win-if-dotenv-differs",
    )
    sdk_env = build_claude_sdk_env(
        settings_obj,
        project_dotenv={"ANTHROPIC_AUTH_TOKEN": "project-token"},
        env_file=env_file,
        project_root=tmp_path,
    )

    assert sdk_env["ANTHROPIC_AUTH_TOKEN"] == "project-token"
    assert sdk_env["ANTHROPIC_API_KEY"] == ""
    assert sdk_env["ANTHROPIC_MODEL"] == ANTHROPIC_SDK_DEFAULTS["ANTHROPIC_MODEL"]
    assert sdk_env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    config_dir = Path(sdk_env["CLAUDE_CONFIG_DIR"])
    assert config_dir.exists()
    assert config_dir.parent == tmp_path.resolve()
