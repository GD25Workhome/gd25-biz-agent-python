"""
调度框架核心类型（与 exhibition 设计 11 对齐）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol


@dataclass
class ChannelBudget:
    """单通道并发与限速预算。"""

    max_concurrency: int
    lock_timeout_sec: int
    request_interval_ms: int = 0
    max_attempts: int = 3


@dataclass
class DiscoverItem:
    """发现阶段单条 URL 结果（纯内存，不写库）。"""

    news_url: str
    title: Optional[str] = None
    published_at: Optional[str] = None
    published_date: Optional[datetime] = None
    content_summary: Optional[str] = None
    external_id: Optional[str] = None
    source: str = "cninfo"


@dataclass
class DiscoverResult:
    """发现执行器返回。"""

    items: list[DiscoverItem] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    stop_reason: Optional[str] = None
    agent_trace_id: Optional[str] = None
    cost_ms: Optional[int] = None


@dataclass
class ContentResult:
    """正文执行器返回。"""

    title: Optional[str] = None
    published_at: Optional[str] = None
    content_text: Optional[str] = None
    content_summary: Optional[str] = None
    content_hash: Optional[str] = None
    actual_channel: Optional[str] = None
    extra: Optional[dict[str, Any]] = None
    agent_trace_id: Optional[str] = None
    cost_ms: Optional[int] = None


class DiscoverExecutor(Protocol):
    """发现执行器：禁止写库。"""

    kind: str

    def execute(self, task: dict[str, Any]) -> DiscoverResult:
        ...


class ContentExecutor(Protocol):
    """正文执行器：禁止写库。"""

    kind: str

    def execute(self, task: dict[str, Any]) -> ContentResult:
        ...
