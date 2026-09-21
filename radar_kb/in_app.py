"""
L2：在 FastAPI 进程内挂载 radar_kb 调度器（daemon 线程）。

默认走 ConcurrentScheduler（跨站并发 + SiteGate）；
``RADAR_KB_CONCURRENT=0`` 时回退旧串行 TaskScheduler。
"""
from __future__ import annotations

import logging
import threading
from typing import List, Optional, Tuple, Union

from radar_kb.async_scheduler import ConcurrentScheduler
from radar_kb.config import load_kb_settings
from radar_kb.scheduler import SchedulerMode, TaskScheduler

log = logging.getLogger("radar_kb.in_app")

# (stop_event, threads)
_Runtime = Tuple[threading.Event, List[threading.Thread]]
_Scheduler = Union[TaskScheduler, ConcurrentScheduler]


def start_radar_kb_in_app(
    *,
    modes: Optional[List[SchedulerMode]] = None,
) -> _Runtime:
    """
        在当前进程拉起 radar_kb 调度线程。

        Args:
            modes: 默认仅 ``["unified"]``。

        Returns:
            (stop_event, threads)
    """
    run_modes: List[SchedulerMode] = list(modes or ["unified"])
    settings = load_kb_settings()
    stop = threading.Event()
    threads: List[threading.Thread] = []

    for mode in run_modes:
        from dataclasses import replace

        mode_settings = replace(settings, worker_id=f"{settings.worker_id}-{mode}")
        if mode_settings.concurrent_enabled:
            scheduler: _Scheduler = ConcurrentScheduler(mode_settings, mode)
            label = "concurrent"
        else:
            scheduler = TaskScheduler(mode_settings, mode)
            label = "legacy-serial"

        def _target(sched: _Scheduler = scheduler) -> None:
            try:
                sched.run_forever(stop_event=stop)
            except Exception:
                log.exception("radar_kb 线程异常退出 mode=%s", getattr(sched, "mode", "?"))

        t = threading.Thread(
            target=_target,
            name=f"radar-kb-{mode}",
            daemon=True,
        )
        t.start()
        threads.append(t)
        log.info(
            "已启动 radar_kb 线程 mode=%s name=%s impl=%s",
            mode,
            t.name,
            label,
        )

    return stop, threads


def stop_radar_kb_in_app(
    stop: threading.Event,
    threads: List[threading.Thread],
    *,
    wait_seconds: float = 30.0,
) -> None:
    """
        优雅停止应用内 radar_kb 线程。

        Args:
            stop: start 返回的事件
            threads: start 返回的线程列表
            wait_seconds: 每线程最长等待
    """
    stop.set()
    for t in threads:
        t.join(timeout=wait_seconds)
        if t.is_alive():
            log.warning("radar_kb 线程未在 %.0fs 内退出 name=%s", wait_seconds, t.name)
        else:
            log.info("radar_kb 线程已停止 name=%s", t.name)
