"""规则二展厅需求 event 分池轮询（event-only）。"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

from backend.domain.tools.deepseek_search_tool import resolve_deepseek_key
from radar_score.config import EVENT_KIND, ScoreSettings, claim_quota
from radar_score.execute import execute_claimed_job
from radar_score.repository import claim_jobs, connect, reclaim_stale

log = logging.getLogger("radar_score.scheduler")


class ScoreScheduler:
    """
        单事件循环里跑 event 任务，用在途数量限制认领。

        展厅需求依赖 DeepSeek Search/Fetch。未配置 DeepSeek 搜索 key 时停领新任务，
        已在跑的任务继续；key 配好后自动恢复认领。
    """

    def __init__(self, settings: ScoreSettings) -> None:
        """
            Args:
                settings: 调度配置
        """
        self.settings = settings
        self._in_flight = 0
        self._tasks: set[asyncio.Task[None]] = set()
        self._event_claim_paused = False

    async def run_forever(self, stop_event: threading.Event) -> None:
        """
            直到 stop_event 置位后返回。

            在途评分会再等 shutdown_wait_sec。超时仍未结束的任务保持 RUNNING，
            由下一轮超时回收退回 PENDING。

            Args:
                stop_event: 停止信号
        """
        log.info(
            "radar_score 启动 locked_by=%s event=%s stale=%ss",
            self.settings.locked_by,
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
        # 2. 展厅需求：未配置 DeepSeek 搜索 key 时不认领，任务留在 PENDING
        if self._event_claim_allowed():
            await self._fill()

    def _event_claim_allowed(self) -> bool:
        """
            今天是否还要认领展厅需求。

            v3 检索链路走 DeepSeek Search/Fetch，只认 DeepSeek 搜索 key
            （`DEEPSEEK_SEARCH_KEY`，回退 `DEEPSEEK_API_KEY`）；未配置时停领 event。
            只在停领与恢复的交界各打一条日志，避免每轮轮询刷屏。

            Returns:
                配了 DeepSeek 搜索 key 时为 True
        """
        live = resolve_deepseek_key() is not None
        if not live and not self._event_claim_paused:
            self._event_claim_paused = True
            log.warning("未配置 DeepSeek 搜索 key（DEEPSEEK_SEARCH_KEY），暂停认领展厅需求任务")
        elif live and self._event_claim_paused:
            self._event_claim_paused = False
            log.info("DeepSeek 搜索 key 已就绪，恢复认领展厅需求任务")
        return live

    def _reclaim(self) -> None:
        conn = connect(self.settings)
        try:
            reclaim_stale(conn, self.settings)
        finally:
            conn.close()

    async def _fill(self) -> None:
        quota = claim_quota(self.settings.event_concurrency, self._in_flight)
        if quota <= 0:
            return
        job_ids = await asyncio.to_thread(self._claim, quota)
        for job_id in job_ids:
            self._in_flight += 1
            task = asyncio.create_task(
                self._run_one(job_id),
                name=f"radar-score-event-{job_id}",
            )
            self._tasks.add(task)

    def _claim(self, limit: int) -> list[int]:
        conn = connect(self.settings)
        try:
            return claim_jobs(conn, self.settings, EVENT_KIND, limit)
        finally:
            conn.close()

    async def _run_one(self, job_id: int) -> None:
        try:
            await execute_claimed_job(self.settings, EVENT_KIND, job_id)
        except Exception:
            log.exception("任务执行失败 kind=%s jobId=%s", EVENT_KIND, job_id)
        finally:
            self._in_flight -= 1
            current: Optional[asyncio.Task[None]] = asyncio.current_task()
            if current is not None:
                self._tasks.discard(current)

    def _sleep_seconds(self) -> float:
        if self._in_flight:
            return min(2.0, self.settings.poll_interval_sec)
        return self.settings.poll_interval_sec

    async def _wait(self, stop_event: threading.Event, seconds: float) -> None:
        remaining = max(0.0, seconds)
        while remaining > 0 and not stop_event.is_set():
            step = min(1.0, remaining)
            await asyncio.sleep(step)
            remaining -= step
