"""
统一站点闸门 SiteGate：按归一化 host 同站串行 + 请求结束后冷却。

设计文档：ai_docs/26092102-列表正文跨站并发同站串行设计.md

语义要点：
  - 主键 = 归一化 host（非裸 source_url_id）
  - 冷却 sleep 在锁外，持锁区间仅覆盖实际 HTTP
  - 优先级 DISCOVER > CONTENT，带 aging 防止详情饿死
  - 同步门面与异步门面共享 next_allowed / 互斥状态（供 cninfo to_thread）
"""
from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from enum import IntEnum
from typing import AsyncIterator, Dict, Iterator, Optional
from urllib.parse import urlparse

log = logging.getLogger("radar_kb.site_gate")


class GatePriority(IntEnum):
    """闸门等待优先级：数值越小越优先。"""

    DISCOVER = 0
    CONTENT = 1


def normalize_host(url_or_host: str) -> str:
    """
        归一化 host：小写、去 www.；纯 host 也可传入。

        Args:
            url_or_host: URL 或 host 字符串

        Returns:
            归一化 host；无法解析时返回空串
    """
    text = (url_or_host or "").strip()
    if not text:
        return ""
    if "://" not in text and "/" not in text:
        host = text.lower()
    else:
        try:
            host = (urlparse(text).hostname or "").strip().lower()
        except Exception:
            return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def host_from_task(task: dict) -> str:
    """
        从任务行提取闸门 host。

        优先 url / seed_url；缺失时返回空（调用方应回退全局键）。
    """
    for key in ("url", "seed_url"):
        host = normalize_host(str(task.get(key) or ""))
        if host:
            return host
    return ""


@dataclass
class _HostState:
    """
        单 host 闸门状态。

        互斥只用 threading.Lock，便于 async（to_thread acquire）与 sync 真正串行；
        next_allowed_at 两边共享。
    """

    hold_lock: threading.Lock
    next_allowed_at: float = 0.0
    # 连续被 DISCOVER 抢占次数（aging）
    discover_streak: int = 0
    content_wait_count: int = 0


class SiteGate:
    """
        进程内站点闸门。

        异步路径用 ``hold_for_request``；同步路径（cninfo）用 ``hold_for_request_sync``。
        二者共享 ``next_allowed_at``，避免双重节奏或互不知情。
    """

    def __init__(
        self,
        *,
        gap_min_sec: float = 5.0,
        gap_max_sec: float = 9.0,
        aging_after_discover: int = 3,
    ) -> None:
        """
            Args:
                gap_min_sec: 同站冷却下限（秒）
                gap_max_sec: 同站冷却上限（秒）
                aging_after_discover: 同站连续 discover 抢占达到该次数后，
                    下一次放行排队中的 content（0 表示关闭 aging）
        """
        self.gap_min_sec = max(0.0, float(gap_min_sec))
        self.gap_max_sec = max(self.gap_min_sec, float(gap_max_sec))
        self.aging_after_discover = max(0, int(aging_after_discover))
        self._states: Dict[str, _HostState] = {}
        self._meta_lock = threading.Lock()

    def _state(self, host: str) -> _HostState:
        """获取或创建 host 状态（线程安全）。"""
        key = host or "__global__"
        with self._meta_lock:
            st = self._states.get(key)
            if st is None:
                st = _HostState(hold_lock=threading.Lock())
                self._states[key] = st
            return st

    def _roll_gap(self) -> float:
        """抽样一次冷却秒数。"""
        if self.gap_max_sec <= self.gap_min_sec:
            return self.gap_min_sec
        return random.uniform(self.gap_min_sec, self.gap_max_sec)

    def seconds_until_ready(self, host: str, now: Optional[float] = None) -> float:
        """
            距离该 host 可发下一请求还需等待的秒数。

            Returns:
                >=0；0 表示已到点
        """
        ts = float(now if now is not None else time.monotonic())
        st = self._state(host)
        return max(0.0, float(st.next_allowed_at) - ts)

    def is_ready(self, host: str, now: Optional[float] = None) -> bool:
        """该 host 是否已过冷却（不保证此刻无人占用）。"""
        return self.seconds_until_ready(host, now) <= 0.0

    async def wait_until_ready(self, host: str) -> float:
        """
            在锁外等到冷却结束（不占业务互斥）。

            Returns:
                实际等待秒数
        """
        waited = 0.0
        while True:
            delay = self.seconds_until_ready(host)
            if delay <= 0:
                return waited
            await asyncio.sleep(min(delay, 1.0))
            waited += min(delay, 1.0)

    def wait_until_ready_sync(self, host: str) -> float:
        """同步版：锁外等到冷却结束。"""
        waited = 0.0
        while True:
            delay = self.seconds_until_ready(host)
            if delay <= 0:
                return waited
            time.sleep(min(delay, 1.0))
            waited += min(delay, 1.0)

    def _effective_priority(self, host: str, priority: GatePriority) -> GatePriority:
        """
            应用 aging：content 等待且 discover 连胜达阈值时，提升为与 discover 同级抢锁。
        """
        if priority != GatePriority.CONTENT or self.aging_after_discover <= 0:
            return priority
        st = self._state(host)
        if st.discover_streak >= self.aging_after_discover and st.content_wait_count > 0:
            log.info(
                "SiteGate aging 放行 content host=%s discover_streak=%s",
                host or "__global__",
                st.discover_streak,
            )
            return GatePriority.DISCOVER
        return priority

    @asynccontextmanager
    async def hold_for_request(
        self,
        host: str,
        priority: GatePriority = GatePriority.CONTENT,
    ) -> AsyncIterator[None]:
        """
            异步：锁外冷却 → 持锁（仅 HTTP 期间）→ 结束后写 next_allowed。

            Args:
                host: 归一化 host（空则走全局键）
                priority: DISCOVER / CONTENT；同锁竞争时 discover 优先（配合 aging）
        """
        key = host or "__global__"
        st = self._state(key)
        eff = self._effective_priority(key, priority)
        if priority == GatePriority.CONTENT:
            st.content_wait_count += 1

        # 1. 锁外等到冷却（不占 hold_lock）
        wait_cool = await self.wait_until_ready(key)

        # 2. 简易优先：content 未 aging 时稍让 discover
        if eff > GatePriority.DISCOVER:
            for _ in range(3):
                if not st.hold_lock.locked():
                    break
                await asyncio.sleep(0.05)

        t0 = time.monotonic()
        # 与 sync 路径共用同一把锁，避免异步正文与同步巨潮重叠
        await asyncio.to_thread(st.hold_lock.acquire)
        wait_lock = time.monotonic() - t0
        if priority == GatePriority.CONTENT:
            st.content_wait_count = max(0, st.content_wait_count - 1)

        log.info(
            "SiteGate acquire host=%s priority=%s wait_cool_ms=%.0f wait_lock_ms=%.0f",
            key,
            priority.name,
            wait_cool * 1000,
            wait_lock * 1000,
        )
        try:
            extra = self.seconds_until_ready(key)
            if extra > 0:
                await asyncio.sleep(extra)
            yield
        finally:
            gap = self._roll_gap()
            st.next_allowed_at = time.monotonic() + gap
            if priority == GatePriority.DISCOVER:
                st.discover_streak += 1
            else:
                st.discover_streak = 0
            st.hold_lock.release()
            log.info(
                "SiteGate release host=%s priority=%s gap_ms=%.0f next_in=%.1fs",
                key,
                priority.name,
                gap * 1000,
                gap,
            )

    @contextmanager
    def hold_for_request_sync(
        self,
        host: str,
        priority: GatePriority = GatePriority.CONTENT,
    ) -> Iterator[None]:
        """
            同步门面：与异步共享 next_allowed；用于 cninfo 等 to_thread 路径。
        """
        key = host or "__global__"
        st = self._state(key)
        wait_cool = self.wait_until_ready_sync(key)
        t0 = time.monotonic()
        st.hold_lock.acquire()
        wait_lock = time.monotonic() - t0
        log.info(
            "SiteGate sync acquire host=%s priority=%s wait_cool_ms=%.0f wait_lock_ms=%.0f",
            key,
            priority.name,
            wait_cool * 1000,
            wait_lock * 1000,
        )
        try:
            extra = self.seconds_until_ready(key)
            if extra > 0:
                time.sleep(extra)
            yield
        finally:
            gap = self._roll_gap()
            st.next_allowed_at = time.monotonic() + gap
            if priority == GatePriority.DISCOVER:
                st.discover_streak += 1
            else:
                st.discover_streak = 0
            st.hold_lock.release()
            log.info(
                "SiteGate sync release host=%s priority=%s gap_ms=%.0f",
                key,
                priority.name,
                gap * 1000,
            )


# ----- 进程级单例（供 crawl_tools / fetcher 注入）-----

_shared_gate: Optional[SiteGate] = None
_shared_gate_lock = threading.Lock()


def get_shared_site_gate() -> Optional[SiteGate]:
    """返回进程内 SiteGate；未初始化时为 None（调用方走旧限速）。"""
    return _shared_gate


def set_shared_site_gate(gate: Optional[SiteGate]) -> None:
    """设置或清空进程内 SiteGate。"""
    global _shared_gate
    with _shared_gate_lock:
        _shared_gate = gate


def reset_shared_site_gate() -> None:
    """测试用：清空共享闸门。"""
    set_shared_site_gate(None)
