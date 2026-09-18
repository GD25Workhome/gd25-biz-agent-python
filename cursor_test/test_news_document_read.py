"""
news_document_read.load_document_for_agent 单元测试（mock DB）。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

import pytest

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.domain.knowledge import news_document_read as mod


@pytest.mark.asyncio
async def test_load_document_company_mismatch() -> None:
    """company_id 不匹配时返回 error dict。"""
    with patch.object(
        mod.settings.__class__, "is_exhibition_mysql_enabled", return_value=True
    ), patch.object(mod, "run_db", return_value=None):
        out = await mod.load_document_for_agent(1, 999)
    assert out["ok"] is False
    assert "不匹配" in out["error"] or "不存在" in out["error"]


@pytest.mark.asyncio
async def test_load_document_deleted_or_missing() -> None:
    """无行时返回 error。"""
    with patch.object(
        mod.settings.__class__, "is_exhibition_mysql_enabled", return_value=True
    ), patch.object(mod, "run_db", return_value=None):
        out = await mod.load_document_for_agent(404, 1)
    assert out["ok"] is False


@pytest.mark.asyncio
async def test_load_document_truncation_and_fallback() -> None:
    """正文截断与 summary 回退。"""
    row = {
        "id": 7,
        "company_id": 100,
        "title": "标题",
        "url": "https://example.com/a",
        "content_text": "x" * 50,
        "content_summary": "摘要",
        "content_grade": "full",
        "source_kind": "cninfo",
        "fetch_status": 1,
    }

    async def _fake_run_db(fn, sql, params):  # noqa: ANN001
        return row

    with patch.object(
        mod.settings.__class__, "is_exhibition_mysql_enabled", return_value=True
    ), patch.object(mod, "run_db", side_effect=_fake_run_db):
        out = await mod.load_document_for_agent(7, 100, max_chars=10)

    assert out["ok"] is True
    assert out["truncated"] is True
    assert len(out["content"]) == 10
    assert out["evidence_strength"] == "full"


@pytest.mark.asyncio
async def test_load_document_fallback_title() -> None:
    """无正文无摘要时回退 title。"""
    row = {
        "id": 8,
        "company_id": 100,
        "title": "仅标题",
        "url": "",
        "content_text": "",
        "content_summary": "",
        "content_grade": "stub",
        "source_kind": "news_html",
        "fetch_status": 1,
    }

    with patch.object(
        mod.settings.__class__, "is_exhibition_mysql_enabled", return_value=True
    ), patch.object(mod, "run_db", return_value=row):
        out = await mod.load_document_for_agent(8, 100)

    assert out["ok"] is True
    assert out["content"] == "仅标题"
    assert out["evidence_strength"] == "title_only"
