"""
radar_kb 统一入口。

默认不随 FastAPI 启动（RADAR_KB_WORKER_IN_APP=false）。
本机或独立进程：python -m radar_kb［unified|discover|content|all］
test 要把写入挂进 Agent 进程时，由发布页设 RADAR_KB_WORKER_IN_APP=true。
"""
from __future__ import annotations

import logging
import multiprocessing
import sys
import time
from typing import List

from radar_kb.async_scheduler import ConcurrentScheduler
from radar_kb.config import load_kb_settings
from radar_kb.scheduler import TaskScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
log = logging.getLogger("radar_kb.main")


def _make_scheduler(mode: str):
    """按配置创建并发或串行调度器。"""
    settings = load_kb_settings()
    if settings.concurrent_enabled:
        log.info("使用 ConcurrentScheduler（RADAR_KB_CONCURRENT=1）")
        return ConcurrentScheduler(settings, mode)  # type: ignore[arg-type]
    log.info("使用 TaskScheduler 串行（RADAR_KB_CONCURRENT=0）")
    return TaskScheduler(settings, mode)  # type: ignore[arg-type]


def _run_unified() -> None:
    _make_scheduler("unified").run_forever()


def _run_discover() -> None:
    _make_scheduler("discover").run_forever()


def _run_content() -> None:
    _make_scheduler("content").run_forever()


def main(argv: list[str] | None = None) -> None:
    """
        启动 radar_kb 调度器。

        Args:
            argv: 子命令 unified | discover | content | all
    """
    args = list(sys.argv if argv is None else argv)
    mode = (args[1] if len(args) > 1 else "unified").strip().lower()
    if mode in ("unified", "all-in-one", "one"):
        _run_unified()
        return
    if mode == "discover":
        _run_discover()
        return
    if mode == "content":
        _run_content()
        return
    if mode == "all":
        # 兼容旧双进程；新部署请用 unified
        log.warning(
            "mode=all 仍为双进程 discover+content；推荐改用 python -m radar_kb unified"
        )
        procs: List[multiprocessing.Process] = []
        for target, name in ((_run_discover, "discover"), (_run_content, "content")):
            p = multiprocessing.Process(target=target, name=f"radar-kb-{name}")
            p.start()
            log.info("已启动子进程 name=%s pid=%s", name, p.pid)
            procs.append(p)
        try:
            while True:
                for p in procs:
                    if not p.is_alive():
                        raise SystemExit(f"子进程退出 name={p.name} code={p.exitcode}")
                time.sleep(2.0)
        except KeyboardInterrupt:
            for p in procs:
                p.terminate()
        return
    raise SystemExit(
        f"未知模式: {mode!r}，请使用 unified | discover | content | all"
    )


if __name__ == "__main__":
    main()
