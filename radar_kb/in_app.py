"""
L2：在 FastAPI 进程内挂载 radar_kb 统一调度器（单线程单 loop）。

同步扫表循环跑在 daemon 线程里，避免阻塞 asyncio 事件循环。
独立 CLI（python -m radar_kb）仍可用，便于排障。
"""
from __future__ import annotations

import logging
import threading
from typing import List, Optional, Tuple

from radar_kb.config import load_kb_settings
from radar_kb.scheduler import SchedulerMode, TaskScheduler

log = logging.getLogger("radar_kb.in_app")

# (stop_event, threads)
_Runtime = Tuple[threading.Event, List[threading.Thread]]


def start_radar_kb_in_app(
    *,
    modes: Optional[List[SchedulerMode]] = None,
) -> _Runtime:
    """
        在当前进程拉起 radar_kb 调度线程。

        Args:
            modes: 默认仅 ``["unified"]``（单 loop：发现优先 + 自适应休息）。
                   传入 ``discover`` / ``content`` 可回到旧双线程排障模式。

        Returns:
            (stop_event, threads)：关闭时先 stop.set()，再 join 线程
    """
    run_modes: List[SchedulerMode] = list(modes or ["unified"])
    settings = load_kb_settings()
    stop = threading.Event()
    threads: List[threading.Thread] = []

    for mode in run_modes:
        # 每模式独立 worker_id，避免 locked_by 冲突（多 mode 排障时）
        from dataclasses import replace

        mode_settings = replace(settings, worker_id=f"{settings.worker_id}-{mode}")
        scheduler = TaskScheduler(mode_settings, mode)

        def _target(sched: TaskScheduler = scheduler) -> None:
            try:
                sched.run_forever(stop_event=stop)
            except Exception:
                log.exception("radar_kb 线程异常退出 mode=%s", sched.mode)

        t = threading.Thread(
            target=_target,
            name=f"radar-kb-{mode}",
            daemon=True,
        )
        t.start()
        threads.append(t)
        log.info("已启动 radar_kb 线程 mode=%s name=%s", mode, t.name)

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
