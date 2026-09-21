"""
规则版详情页抓取（T1.4 第一段）。

职责：`HTTP GET 详情页 → ContentExtractor.extract_article()`，产出可直接入库的
title / published_at / content_text / content_summary / content_hash。

⚠️ 抽取器是**原地复用**的：`company_news_crawl.adapters.content_extractor.ContentExtractor`
（trafilatura 主 + selectolax 回退），本模块不重复实现抽取逻辑，只做
「抓 + 限速 + 重试 + 成败判定」。

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md` §3.1-1
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from backend.domain.news_crawl.crawl_tools import USER_AGENT
from backend.domain.news_content.rate_limiter import SiteRateLimiter
from company_news_crawl.adapters.content_extractor import ContentExtractor, ExtractedArticle

logger = logging.getLogger(__name__)

# 可选：radar_kb SiteGate（延迟导入避免环依赖）
try:
    from radar_kb.site_gate import GatePriority, SiteGate
except Exception:  # pragma: no cover
    SiteGate = None  # type: ignore
    GatePriority = None  # type: ignore

# 与 news_crawl 的列表页抓取同一套头，避免同一站点对两个链路的 UA 策略不一致
_ACCEPT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_client: Optional[httpx.AsyncClient] = None


def get_http_client(timeout: float) -> httpx.AsyncClient:
    """
    共享 AsyncClient（进程级单例，保留连接复用）。

    由 worker 在启动/退出时通过 `close_http_client()` 成对管理。
    """
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=_ACCEPT_HEADERS,
        )
    return _client


async def close_http_client() -> None:
    """关闭共享 AsyncClient（worker 优雅退出时调用）。"""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
        _client = None


@dataclass
class RuleFetchResult:
    """一次规则版抓取的结果。"""

    url: str
    final_url: str
    http_status: int
    ok: bool
    article: Optional[ExtractedArticle]
    error: Optional[str]
    attempts: int
    duration_ms: int


async def fetch_article_by_rule(
    url: str,
    *,
    site_key: str | None,
    limiter: SiteRateLimiter,
    min_chars: int,
    summary_max_length: int,
    timeout: float,
    max_retries: int = 1,
    site_gate: "SiteGate | None" = None,
    gate_host: str | None = None,
    gate_priority: "GatePriority | None" = None,
) -> RuleFetchResult:
    """
        规则版抓取一篇详情页并抽取正文。

        若传入 ``site_gate``，则每次 HTTP 经闸门持锁（同站串行+冷却），不再走 limiter。

        Args:
            url: 详情页 URL
            site_key: 旧限速用站点键
            limiter: 无 SiteGate 时使用的限速器
            min_chars: 正文最短字符数
            summary_max_length: 摘要字数
            timeout: 单次请求超时（秒）
            max_retries: 额外重试次数
            site_gate: 可选统一站点闸门
            gate_host: 闸门 host
            gate_priority: 闸门优先级

        Returns:
            RuleFetchResult
    """
    started = time.monotonic()
    client = get_http_client(timeout)
    total_attempts = max(1, int(max_retries) + 1)
    last_error: Optional[str] = None
    http_status = 0
    final_url = url
    html: Optional[str] = None

    for attempt in range(1, total_attempts + 1):
        try:
            if site_gate is not None:
                from radar_kb.site_gate import GatePriority as GP
                from radar_kb.site_gate import normalize_host

                host = gate_host or normalize_host(url)
                prio = gate_priority if gate_priority is not None else GP.CONTENT
                async with site_gate.hold_for_request(host, prio):
                    response = await client.get(url)
            else:
                await limiter.acquire(site_key)
                response = await client.get(url)
            http_status = response.status_code
            final_url = str(response.url)
            if http_status != 200:
                last_error = f"HTTP {http_status}"
            else:
                html = response.text
                break
        except httpx.TimeoutException:
            last_error = "Timeout"
        except httpx.ConnectError as exc:
            last_error = f"Connection error: {type(exc).__name__}"
        except Exception as exc:  # 含解码异常等
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < total_attempts:
            logger.debug(
                "规则抓取重试 %d/%d url=%s err=%s",
                attempt,
                total_attempts,
                url,
                last_error,
            )

    duration_ms = int((time.monotonic() - started) * 1000)

    if html is None:
        return RuleFetchResult(
            url=url,
            final_url=final_url,
            http_status=http_status,
            ok=False,
            article=None,
            error=last_error or "抓取失败",
            attempts=total_attempts,
            duration_ms=duration_ms,
        )

    article = ContentExtractor.extract_article(
        html,
        final_url or url,
        summary_max_length=summary_max_length,
    )

    if not article.satisfies(min_chars):
        got = len((article.content_text or "").strip())
        return RuleFetchResult(
            url=url,
            final_url=final_url,
            http_status=http_status,
            ok=False,
            article=article,
            error=f"正文过短或抽取失败（{got} < {int(min_chars)} 字符）",
            attempts=total_attempts,
            duration_ms=duration_ms,
        )

    return RuleFetchResult(
        url=url,
        final_url=final_url,
        http_status=http_status,
        ok=True,
        article=article,
        error=None,
        attempts=total_attempts,
        duration_ms=duration_ms,
    )


def is_rule_fetch_failure(result: RuleFetchResult) -> bool:
    """语义化判断：本次规则抓取是否失败（失败才走 Agent 兜底）。"""
    return not result.ok
