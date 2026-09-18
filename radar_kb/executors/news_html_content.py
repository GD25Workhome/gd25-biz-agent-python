"""
news_html 正文执行器：规则抓取 + 可选 Agent 兜底，不写库。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from backend.app.config import settings
from backend.domain.news_content.agent_fallback import AgentFallbackGuard, run_detail_fetch_agent
from backend.domain.news_content.constants import CHANNEL_AGENT, CHANNEL_RULE
from backend.domain.news_content.content_fetcher import fetch_article_by_rule
from backend.domain.news_content.rate_limiter import get_shared_site_rate_limiter
from radar_kb.types import ContentResult


class NewsHtmlContentExecutor:
    """HTML 详情页正文。"""

    kind = "news_html"

    def execute(self, task: dict[str, Any]) -> ContentResult:
        """
        规则抓取，失败时尝试 Agent 兜底一次。

        Args:
            task: content_task 行

        Returns:
            ContentResult
        """
        return asyncio.run(self._execute_async(task))

    async def _execute_async(self, task: dict[str, Any]) -> ContentResult:
        started = time.monotonic()
        url = (task.get("url") or "").strip()
        source_url_id = int(task.get("source_url_id") or 0)
        site_key = str(source_url_id or "")
        # 进程级单例：跨任务累计同站间隔（Frontier 另有 gap，二者叠加取更保守）
        limiter = get_shared_site_rate_limiter()
        guard = AgentFallbackGuard(
            enabled=settings.NEWS_CONTENT_AGENT_FALLBACK_ENABLED,
            daily_quota=settings.NEWS_CONTENT_AGENT_DAILY_QUOTA,
            max_consecutive_failures=settings.NEWS_CONTENT_AGENT_MAX_CONSECUTIVE_FAILURES,
            max_content_failures_per_site=settings.NEWS_CONTENT_AGENT_MAX_CONTENT_FAILURES_PER_SITE,
        )

        channel: Optional[str] = None
        agent_trace_id: Optional[str] = None
        error_message: Optional[str] = None

        rule_result = await fetch_article_by_rule(
            url,
            site_key=site_key,
            limiter=limiter,
            min_chars=settings.NEWS_CONTENT_FETCH_MIN_CHARS,
            summary_max_length=settings.NEWS_CONTENT_SUMMARY_MAX_LENGTH,
            timeout=settings.NEWS_CONTENT_HTTP_TIMEOUT_SECONDS,
            max_retries=settings.NEWS_CONTENT_HTTP_MAX_RETRIES,
        )
        article = rule_result.article if rule_result.ok else None
        if article is not None:
            channel = CHANNEL_RULE
        else:
            error_message = rule_result.error or "规则抓取失败"
            allowed, reason = await guard.allow(source_url_id)
            if allowed:
                quota_ok, quota_reason = await guard.try_consume_quota()
                if quota_ok:
                    trace_id = f"radar-kb-content-{task.get('id')}-{int(time.time())}"
                    agent_result = await run_detail_fetch_agent(
                        url=url, site_key=site_key, limiter=limiter, trace_id=trace_id
                    )
                    agent_trace_id = agent_result.trace_id
                    await guard.mark_result(
                        success=agent_result.ok,
                        source_url_id=source_url_id,
                        failure_kind=agent_result.failure_kind,
                        content_streak_eligible=bool(agent_result.content_streak_eligible),
                    )
                    if agent_result.ok and agent_result.article is not None:
                        article = agent_result.article
                        channel = CHANNEL_AGENT
                        error_message = None

        cost_ms = int((time.monotonic() - started) * 1000)
        if article is None or not article.content_text:
            return ContentResult(
                actual_channel=channel,
                extra={"error": error_message or "fetch_failed"},
                agent_trace_id=agent_trace_id,
                cost_ms=cost_ms,
            )

        return ContentResult(
            title=article.title,
            published_at=article.published_at,
            content_text=article.content_text,
            content_summary=article.content_summary,
            content_hash=article.content_hash,
            actual_channel=channel or CHANNEL_RULE,
            agent_trace_id=agent_trace_id,
            cost_ms=cost_ms,
        )
