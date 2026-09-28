"""
radar_score 独立入口。

默认不随 FastAPI 启动（RADAR_SCORE_WORKER_IN_APP=false）。
本机或独立进程：python -m radar_score
要挂进 Agent 进程时，设 RADAR_SCORE_WORKER_IN_APP=true。
"""
from __future__ import annotations

import asyncio
import logging
import signal
import threading

from radar_score.config import load_score_settings
from radar_score.scheduler import ScoreScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
log = logging.getLogger("radar_score.main")


def main() -> None:
    """启动评分调度，直到收到 SIGINT / SIGTERM。"""
    settings = load_score_settings()
    stop = threading.Event()

    def _stop(*_args: object) -> None:
        log.info("收到停止信号")
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    asyncio.run(ScoreScheduler(settings).run_forever(stop))


if __name__ == "__main__":
    main()
