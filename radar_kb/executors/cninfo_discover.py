"""
巨潮发现执行器：只检索，不写库。
"""
from __future__ import annotations

import time
from typing import Any

from radar_crawl.adapters import cninfo
from radar_kb.config import KbSettings
from radar_kb.types import DiscoverItem, DiscoverResult


class CninfoDiscoverExecutor:
    """巨潮公告列表发现。"""

    kind = "cninfo"

    def __init__(self, settings: KbSettings) -> None:
        self._settings = settings

    def execute(self, task: dict[str, Any]) -> DiscoverResult:
        """
        检索巨潮并映射为 DiscoverItem 列表。

        Args:
            task: 已抢锁的 crawl_task 行

        Returns:
            DiscoverResult（纯内存）
        """
        started = time.monotonic()
        company_name = (task.get("company_name") or "").strip()
        stock_code = (task.get("stock_code") or "").strip()
        if not company_name or not stock_code:
            raise RuntimeError("缺少 company_name 或 stock_code，无法检索巨潮")

        time_from = task.get("time_from")
        time_to = task.get("time_to")
        sdate = time_from.strftime("%Y-%m-%d") if hasattr(time_from, "strftime") else str(time_from)
        edate = time_to.strftime("%Y-%m-%d") if hasattr(time_to, "strftime") else str(time_to)

        raw_list = cninfo.search_announcements(
            company_name,
            sdate=sdate,
            edate=edate,
            page_size=self._settings.cninfo_page_size,
            max_pages=self._settings.cninfo_max_pages,
        )
        matched = cninfo.filter_by_stock_code(raw_list, stock_code)

        items: list[DiscoverItem] = []
        for item in matched:
            external_id = str(item.get("announcementId") or item.get("id") or "") or None
            pdf_url = cninfo.build_pdf_url(item.get("adjunctUrl"))
            url = pdf_url or item.get("url") or ""
            if not url:
                continue
            title = (item.get("announcementTitle") or item.get("shortTitle") or "")[:512]
            summary = cninfo.make_summary(
                item.get("announcementContent"),
                title,
                self._settings.summary_max_chars,
            )
            published_dt = cninfo.parse_announcement_time(item.get("announcementTime"))
            published_at = (
                published_dt.strftime("%Y-%m-%d") if published_dt else None
            )
            items.append(
                DiscoverItem(
                    news_url=url,
                    title=title,
                    published_at=published_at,
                    published_date=published_dt,
                    content_summary=summary,
                    external_id=external_id,
                    source="cninfo",
                )
            )

        cost_ms = int((time.monotonic() - started) * 1000)
        stats = {
            "searched": len(raw_list),
            "matched": len(matched),
            "mapped": len(items),
        }
        return DiscoverResult(items=items, stats=stats, cost_ms=cost_ms)
