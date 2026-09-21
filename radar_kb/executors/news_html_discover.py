"""
企业官网 HTML 发现执行器（Agent 列表），不写库。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

from radar_kb.config import KbSettings
from radar_kb.site_gate import SiteGate, get_shared_site_gate
from radar_kb.types import DiscoverItem, DiscoverResult


class NewsHtmlDiscoverExecutor:
    """news_html 通道发现。"""

    kind = "news_html"

    def __init__(self, settings: KbSettings) -> None:
        self._settings = settings

    def execute(self, task: dict[str, Any]) -> DiscoverResult:
        """同步门面：旧串行调度器用。"""
        return asyncio.run(self.execute_async(task))

    async def execute_async(
        self,
        task: dict[str, Any],
        *,
        site_gate: Optional[SiteGate] = None,
    ) -> DiscoverResult:
        """
            调用 run_news_crawl_agent 拉列表 URL。

            Args:
                task: crawl_task 行
                site_gate: 可选闸门；默认进程共享

            Returns:
                DiscoverResult
        """
        from backend.domain.news_crawl.agent_runner import run_news_crawl_agent

        started = time.monotonic()
        seed_url = (task.get("seed_url") or "").strip()
        if not seed_url:
            raise RuntimeError("缺少 seed_url")

        known: list[str] = []
        raw_known = task.get("known_urls_json")
        if raw_known:
            try:
                parsed = (
                    json.loads(raw_known) if isinstance(raw_known, str) else raw_known
                )
                if isinstance(parsed, list):
                    known = [str(x) for x in parsed if x]
            except (TypeError, ValueError):
                known = []

        max_pages = int(task.get("max_pages") or 3)
        gate = site_gate if site_gate is not None else get_shared_site_gate()
        agent_out = await run_news_crawl_agent(
            seed_url=seed_url,
            known_urls=known,
            company_name=(task.get("company_name") or ""),
            stock_code=(task.get("stock_code") or ""),
            max_pages=max_pages,
            trace_id=f"radar-kb-discover-{task.get('id')}",
            site_gate=gate,
        )

        items: list[DiscoverItem] = []
        for row in agent_out.get("news_urls") or []:
            url = (row.get("url") or "").strip()
            if not url:
                continue
            items.append(
                DiscoverItem(
                    news_url=url,
                    title=(row.get("title") or None),
                    published_at=row.get("published_at"),
                    content_summary=(row.get("title") or "")[:500] or None,
                    source="agent",
                )
            )

        cost_ms = int((time.monotonic() - started) * 1000)
        stats = dict(agent_out.get("stats") or {})
        stats["mapped"] = len(items)
        return DiscoverResult(
            items=items,
            stats=stats,
            stop_reason=agent_out.get("stop_reason"),
            cost_ms=cost_ms,
        )
