"""
在 FastAPI 进程内挂载 radar_score（daemon 线程）。

默认关闭。RADAR_SCORE_WORKER_IN_APP=true 时由 backend/main.py lifespan 启动。
也可单独运行：python -m radar_score
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import List, Tuple

from radar_score.config import load_score_settings
from radar_score.scheduler import ScoreScheduler

log = logging.getLogger("radar_score.in_app")

_Runtime = Tuple[threading.Event, List[threading.Thread]]


def start_radar_score_in_app() -> _Runtime:
    """
        在当前进程拉起评分调度线程。

        Returns:
            (stop_event, threads)

        Raises:
            RuntimeError: 未配置 MySQL 或 Java 基址
    """
    settings = load_score_settings()
    stop = threading.Event()
    scheduler = ScoreScheduler(settings)

    def _target() -> None:
        try:
            asyncio.run(scheduler.run_forever(stop))
        except Exception:
            log.exception("radar_score 线程异常退出")

    thread = threading.Thread(target=_target, name="radar-score", daemon=True)
    thread.start()
    log.info(
        "已启动 radar_score 线程 name=%s profile=%s event=%s",
        thread.name,
        settings.profile_concurrency,
        settings.event_concurrency,
    )
    return stop, [thread]


def stop_radar_score_in_app(
    stop: threading.Event,
    threads: List[threading.Thread],
    *,
    wait_seconds: float = 30.0,
) -> None:
    """
        通知调度线程停止并等待退出。

        Args:
            stop: start 返回的事件
            threads: start 返回的线程列表
            wait_seconds: 每线程最长等待
    """
    stop.set()
    for thread in threads:
        thread.join(timeout=wait_seconds)
        if thread.is_alive():
            log.warning("radar_score 线程未在 %.0fs 内退出 name=%s", wait_seconds, thread.name)
        else:
            log.info("radar_score 线程已停止 name=%s", thread.name)
