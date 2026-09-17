"""
巨潮 PDF 正文执行器：只下载抽字，不写库。
"""
from __future__ import annotations

import time
from typing import Any

from radar_crawl.adapters import cninfo
from radar_kb.config import KbSettings
from radar_kb.repository import sha1_hex
from radar_kb.types import ContentResult


class CninfoPdfExecutor:
    """巨潮 PDF 正文抓取。"""

    kind = "cninfo"

    def __init__(self, settings: KbSettings) -> None:
        self._settings = settings

    def execute(self, task: dict[str, Any]) -> ContentResult:
        """
        下载 PDF 并抽取正文。

        Args:
            task: 已抢锁的 content_task 行

        Returns:
            ContentResult
        """
        started = time.monotonic()
        url = (task.get("url") or "").strip()
        if not url:
            return ContentResult(
                actual_channel="pdf_pypdf",
                extra={"error": "missing_url"},
                cost_ms=int((time.monotonic() - started) * 1000),
            )

        text, err = cninfo.download_and_extract_text(
            url,
            max_chars=self._settings.content_text_max_chars,
            max_pages=self._settings.pdf_max_pages,
        )
        cost_ms = int((time.monotonic() - started) * 1000)
        if err or not text:
            return ContentResult(
                actual_channel="pdf_pypdf",
                extra={"error": err or "empty_text"},
                cost_ms=cost_ms,
            )

        title = (task.get("title") or "").strip() or None
        summary = cninfo.make_summary(text, title or "", self._settings.summary_max_chars)
        normalized = " ".join(text.split())
        content_hash = sha1_hex(normalized)
        return ContentResult(
            title=title,
            published_at=task.get("published_at"),
            content_text=text,
            content_summary=summary,
            content_hash=content_hash,
            actual_channel="pdf_pypdf",
            cost_ms=cost_ms,
        )
