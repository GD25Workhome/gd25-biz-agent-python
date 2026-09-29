"""画像、展厅需求分池轮询。每类并发默认 2，与 Java 内存队列的 worker 数对齐。"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

from backend.domain.tools.anysearch_tool import has_live_key
from radar_score.config import EVENT_KIND, PROFILE_KIND, ScoreSettings, claim_quota
from radar_score.execute import execute_claimed_job
from radar_score.java_client import JavaUnavailable
from radar_score.repository import claim_jobs, connect, reclaim_stale

log = logging.getLogger("radar_score.scheduler")


class ScoreScheduler:
    """
        单事件循环里跑两类任务，用在途数量限制认领。

        展厅需求依赖 AnySearch。当天没有存活 key 时停领新的 event 任务，
        已在跑的任务继续；画像不受影响。key 跨日恢复后自动再领。
    """

    def __init__(self, settings: ScoreSettings) -> None:
        """
            Args:
                settings: 调度配置
        """
        self.settings = settings
        self._in_flight = {PROFILE_KIND: 0, EVENT_KIND: 0}
        self._tasks: set[asyncio.Task[None]] = set()
        self._java_down_until = 0.0
        self._event_claim_paused = False

    def concurrency_of(self, kind: str) -> int:
        """
            该类同时在跑的上限。

            Args:
                kind: profile 或 event

            Returns:
                并发数
        """
        if kind == PROFILE_KIND:
            return self.settings.profile_concurrency
        if kind == EVENT_KIND:
            return self.settings.event_concurrency
        raise ValueError(f"未知评分任务类型: {kind}")

    async def run_forever(self, stop_event: threading.Event) -> None:
        """
            直到 stop_event 置位后返回。

            在途评分会再等 shutdown_wait_sec。超时仍未结束的任务保持 RUNNING，
            由下一轮超时回收退回 PENDING。

            Args:
                stop_event: 停止信号
        """
        log.info(
            "radar_score 启动 locked_by=%s profile=%s event=%s stale=%ss",
            self.settings.locked_by,
            self.settings.profile_concurrency,
            self.settings.event_concurrency,
            self.settings.stale_timeout_sec,
        )
        while not stop_event.is_set():
            try:
                await self._tick()
            except Exception:
                log.exception("radar_score 本轮调度失败")
            await self._wait(stop_event, self._sleep_seconds())
        pending = set(self._tasks)
        if pending:
            log.info("停止中，等待在途评分 %s 条", len(pending))
            await asyncio.wait(pending, timeout=self.settings.shutdown_wait_sec)
            left = [task for task in pending if not task.done()]
            if left:
                log.warning("仍有 %s 条评分未结束，保持 RUNNING 等超时回收", len(left))

    async def _tick(self) -> None:
        # 1. 先回收超时锁，再按空闲槽位认领
        await asyncio.to_thread(self._reclaim)
        if time.monotonic() < self._java_down_until:
            return
        await self._fill(PROFILE_KIND)
        # 2. 展厅需求：AnySearch 当天无存活 key 时不认领，任务留在 PENDING
        if self._event_claim_allowed():
            await self._fill(EVENT_KIND)

    def _event_claim_allowed(self) -> bool:
        """
            今天是否还要认领展厅需求。

            只在停领与恢复的交界各打一条日志，避免每轮轮询刷屏。

            Returns:
                有存活 AnySearch key 时为 True
        """
        # has_live_key：当天未被 401/402 或带 request_id 的 403 熔断的 key 才算存活
        live = has_live_key()
        if not live and not self._event_claim_paused:
            self._event_claim_paused = True
            log.warning("AnySearch 当天无存活 key，暂停认领展厅需求任务")
        elif live and self._event_claim_paused:
            self._event_claim_paused = False
            log.info("AnySearch 已有存活 key，恢复认领展厅需求任务")
        return live

    def _reclaim(self) -> None:
        conn = connect(self.settings)
        try:
            reclaim_stale(conn, self.settings)
        finally:
            conn.close()

    async def _fill(self, kind: str) -> None:
        quota = claim_quota(self.concurrency_of(kind), self._in_flight[kind])
        if quota <= 0:
            return
        job_ids = await asyncio.to_thread(self._claim, kind, quota)
        for job_id in job_ids:
            self._in_flight[kind] += 1
            task = asyncio.create_task(
                self._run_one(kind, job_id),
                name=f"radar-score-{kind}-{job_id}",
            )
            self._tasks.add(task)

    def _claim(self, kind: str, limit: int) -> list[int]:
        conn = connect(self.settings)
        try:
            return claim_jobs(conn, self.settings, kind, limit)
        finally:
            conn.close()

    async def _run_one(self, kind: str, job_id: int) -> None:
        try:
            await execute_claimed_job(self.settings, kind, job_id)
        except JavaUnavailable as ex:
            self._java_down_until = time.monotonic() + self.settings.java_down_backoff_sec
            log.warning(
                "Java 不可用，%.0fs 内不再认领 kind=%s jobId=%s err=%s",
                self.settings.java_down_backoff_sec,
                kind,
                job_id,
                ex,
            )
        except Exception:
            log.exception("任务执行失败 kind=%s jobId=%s", kind, job_id)
        finally:
            self._in_flight[kind] -= 1
            current: Optional[asyncio.Task[None]] = asyncio.current_task()
            if current is not None:
                self._tasks.discard(current)

    def _sleep_seconds(self) -> float:
        if self._in_flight[PROFILE_KIND] or self._in_flight[EVENT_KIND]:
            return min(2.0, self.settings.poll_interval_sec)
        if time.monotonic() < self._java_down_until:
            return self.settings.java_down_backoff_sec
        return self.settings.poll_interval_sec

    async def _wait(self, stop_event: threading.Event, seconds: float) -> None:
        remaining = max(0.0, seconds)
        while remaining > 0 and not stop_event.is_set():
            step = min(1.0, remaining)
            await asyncio.sleep(step)
            remaining -= step
