"""
验证数据库可选配置：无 DATABASE_URL / ENABLE_DATABASE=false 时可加载 Settings。
"""
from __future__ import annotations

import os
from typing import Dict, Optional

import pytest
from pydantic import ValidationError


def _build_settings(
    env: Dict[str, Optional[str]],
    *,
    clear_env_file: bool = True,
):
    """
        在隔离环境下构造 Settings，避免读到真实 .env。

        Args:
            env: 写入 os.environ 的键值；值为 None 表示删除该键
            clear_env_file: 是否将 env_file 指到不存在路径，避免加载项目 .env
    """
    from backend.app.config import Settings

    # 1. 应用临时环境变量
    saved: Dict[str, Optional[str]] = {}
    keys = [
        "DATABASE_URL",
        "ENABLE_DATABASE",
        "DOUBAO_API_KEY",
        "OPENAI_API_KEY",
    ]
    for key in keys:
        saved[key] = os.environ.get(key)
        if key in env:
            value = env[key]
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    try:
        # 2. 构造 Settings（可选屏蔽 .env）
        if clear_env_file:
            return Settings(_env_file=None)  # type: ignore[call-arg]
        return Settings()
    finally:
        # 3. 恢复环境变量
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_settings_without_database_url_disables_db() -> None:
    """未配置 DATABASE_URL 时，自动判定为不启用数据库。"""
    settings = _build_settings(
        {
            "DATABASE_URL": None,
            "ENABLE_DATABASE": None,
        }
    )
    assert settings.DATABASE_URL is None
    assert settings.is_database_enabled is False


def test_settings_enable_database_false_even_with_url() -> None:
    """显式 ENABLE_DATABASE=false 时，即使有 URL 也不启用。"""
    settings = _build_settings(
        {
            "DATABASE_URL": (
                "postgresql+psycopg://u:p@localhost:5432/db?sslmode=disable"
            ),
            "ENABLE_DATABASE": "false",
        }
    )
    assert settings.is_database_enabled is False
    with pytest.raises(RuntimeError, match="数据库未启用"):
        _ = settings.ASYNC_DB_URI


def test_settings_auto_enable_when_url_present() -> None:
    """有 DATABASE_URL 且未显式开关时，自动启用数据库。"""
    url = "postgresql+psycopg://u:p@localhost:5432/db?sslmode=disable"
    settings = _build_settings(
        {
            "DATABASE_URL": url,
            "ENABLE_DATABASE": None,
        }
    )
    assert settings.is_database_enabled is True
    assert settings.ASYNC_DB_URI == url


def test_settings_enable_true_without_url_raises() -> None:
    """ENABLE_DATABASE=true 但无 URL 时应校验失败。"""
    with pytest.raises(ValidationError):
        _build_settings(
            {
                "DATABASE_URL": None,
                "ENABLE_DATABASE": "true",
            }
        )
