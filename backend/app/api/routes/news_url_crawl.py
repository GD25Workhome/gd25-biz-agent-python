"""
新闻 URL Agent 抓取路由。

对接 exhibition：POST /api/v1/huayuan/news-url-crawl
同步执行：跑一次 Claude Agent，返回 known_urls 之外的新闻 URL。
无状态、无数据库依赖。

设计文档：华院Agent设计/260914-整体重构/02-gd25侧详细设计.md §3
"""
from __future__ import annotations

import asyncio
import logging
import secrets

from fastapi import APIRouter, HTTPException

from backend.app.api.schemas.news_url_crawl import (
    NewsUrlCrawlRequest,
    NewsUrlCrawlResponse,
    NewsUrlCrawlStats,
)
from backend.app.config import settings
from backend.domain.news_crawl.agent_runner import run_news_crawl_agent
from backend.domain.news_crawl.exceptions import (
    AgentExecutionError,
    ListFetchError,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["新闻URL抓取"])

# 并发信号量：Agent 单次消耗付费额度且跑 2~4 分钟，必须限制同时运行数。
# 超出的请求排队等待（而非拒绝）—— 调用方本就在等，排队更友好；
# 排队过久者会自然触发 600s 墙钟超时并收到 504。
_AGENT_SEMAPHORE: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """
    惰性创建信号量。

    ⚠️ 必须在事件循环内创建（asyncio.Semaphore 绑定该循环），
    因此不能在模块导入时实例化。
    """
    global _AGENT_SEMAPHORE
    if _AGENT_SEMAPHORE is None:
        _AGENT_SEMAPHORE = asyncio.Semaphore(settings.NEWS_CRAWL_MAX_CONCURRENCY)
    return _AGENT_SEMAPHORE


@router.post(
    "/huayuan/news-url-crawl",
    response_model=NewsUrlCrawlResponse,
    summary="从新闻列表入口页发现新闻详情 URL",
)
async def news_url_crawl(data: NewsUrlCrawlRequest) -> NewsUrlCrawlResponse:
    """
    跑一次 Agent，从新闻列表入口页发现新闻详情 URL。

    ⚠️ 同步接口：Agent 实测耗时 2~4 分钟，调用方需给足超时（建议 ≥620s）。

    返回的 news_urls 已减去调用方传入的 known_urls。
    若 stop_reason=no_detail_links，表示站点无法抽取链接（通道问题，可能需 JS 渲染），
    此时 news_urls 为空但仍是 200 —— 调用方应据 stop_reason 决定是否告警。
    """
    if not settings.is_news_crawl_enabled:
        raise HTTPException(
            status_code=503,
            detail="新闻 URL 抓取未启用或未配置 Anthropic 凭证",
        )

    trace_id = data.trace_id or secrets.token_hex(16)
    seed_url = str(data.news_list_url)

    logger.info(
        "[news-url-crawl] start trace=%s seed=%s known=%d max_pages=%d",
        trace_id, seed_url, len(data.known_urls), data.max_pages,
    )

    try:
        async with _get_semaphore():
            result = await asyncio.wait_for(
                run_news_crawl_agent(
                    seed_url=seed_url,
                    known_urls=data.known_urls,
                    company_name=data.company_name or "",
                    stock_code=data.stock_code or "",
                    max_pages=data.max_pages,
                    trace_id=trace_id,
                ),
                timeout=settings.NEWS_CRAWL_TIMEOUT_SECONDS,
            )
    except asyncio.TimeoutError:
        logger.error(
            "[news-url-crawl] timeout trace=%s (>%ds)",
            trace_id, settings.NEWS_CRAWL_TIMEOUT_SECONDS,
        )
        raise HTTPException(
            status_code=504,
            detail=f"Agent 执行超时（>{settings.NEWS_CRAWL_TIMEOUT_SECONDS}s）",
        )
    except ListFetchError as exc:
        # 列表页全部抓取失败 —— 通道或网络问题
        logger.error("[news-url-crawl] list fetch failed trace=%s: %s", trace_id, exc)
        raise HTTPException(status_code=502, detail=f"列表页抓取失败：{exc}")
    except AgentExecutionError as exc:
        logger.error("[news-url-crawl] agent error trace=%s: %s", trace_id, exc)
        raise HTTPException(status_code=502, detail=f"Agent 执行失败：{exc}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[news-url-crawl] unexpected error trace=%s", trace_id)
        raise HTTPException(status_code=502, detail=f"抓取异常：{exc}")

    logger.info(
        "[news-url-crawl] done trace=%s pages=%d new=%d stop=%s cost=%s duration=%sms",
        trace_id, result["list_pages_fetched"], len(result["news_urls"]),
        result["stop_reason"], result["stats"].get("agent_cost_usd"),
        result["stats"].get("duration_ms"),
    )

    return NewsUrlCrawlResponse(
        news_urls=result["news_urls"],
        list_pages_fetched=result["list_pages_fetched"],
        stop_reason=result["stop_reason"],
        stats=NewsUrlCrawlStats(**result["stats"]),
        trace_id=trace_id,
    )
