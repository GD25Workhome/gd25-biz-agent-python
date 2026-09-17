"""
执行器注册表（发现 / 正文）。
"""
from __future__ import annotations

from typing import Callable, Tuple, Type

from radar_kb.config import KbSettings
from radar_kb.executors.cninfo_discover import CninfoDiscoverExecutor
from radar_kb.executors.cninfo_pdf import CninfoPdfExecutor
from radar_kb.executors.news_html_content import NewsHtmlContentExecutor
from radar_kb.executors.news_html_discover import NewsHtmlDiscoverExecutor
from radar_kb.types import ChannelBudget, ContentExecutor, DiscoverExecutor

DiscoverEntry = Tuple[Type[DiscoverExecutor], ChannelBudget, Callable[[KbSettings], DiscoverExecutor]]
ContentEntry = Tuple[Type[ContentExecutor], ChannelBudget, Callable[[KbSettings], ContentExecutor]]


def _discover_cninfo(settings: KbSettings) -> DiscoverExecutor:
    return CninfoDiscoverExecutor(settings)


def _discover_news_html(settings: KbSettings) -> DiscoverExecutor:
    return NewsHtmlDiscoverExecutor(settings)


def _content_cninfo(settings: KbSettings) -> ContentExecutor:
    return CninfoPdfExecutor(settings)


def _content_news_html(_settings: KbSettings) -> ContentExecutor:
    return NewsHtmlContentExecutor()


DISCOVER_REGISTRY: dict[str, DiscoverEntry] = {
    "news_html": (
        NewsHtmlDiscoverExecutor,
        ChannelBudget(max_concurrency=2, lock_timeout_sec=620),
        _discover_news_html,
    ),
    "cninfo": (
        CninfoDiscoverExecutor,
        # 间隔改由 cninfo 适配器进程级限速（5s+抖动）；此处不再叠 sleep
        ChannelBudget(max_concurrency=1, lock_timeout_sec=300, request_interval_ms=0),
        _discover_cninfo,
    ),
}

CONTENT_REGISTRY: dict[str, ContentEntry] = {
    "news_html": (
        NewsHtmlContentExecutor,
        ChannelBudget(max_concurrency=4, lock_timeout_sec=1800, max_attempts=3),
        _content_news_html,
    ),
    "cninfo": (
        CninfoPdfExecutor,
        ChannelBudget(
            # 实际 HTTP 由适配器锁串行；并发声明保持 1，避免误导
            max_concurrency=1,
            lock_timeout_sec=1800,
            request_interval_ms=0,
            max_attempts=3,
        ),
        _content_cninfo,
    ),
}
