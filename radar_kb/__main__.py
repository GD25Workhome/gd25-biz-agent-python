"""
radar_kb 统一入口。

推荐（L2）：随 FastAPI 启动（RADAR_KB_WORKER_IN_APP=true，默认）。
排障/独立部署仍可用：

    python -m radar_kb discover   # 发现调度器
    python -m radar_kb content    # 正文调度器
    python -m radar_kb all        # 两进程各跑一种
"""
from __future__ import annotations

import logging
import multiprocessing
import sys
import time
from typing import List

from radar_kb.config import load_kb_settings
from radar_kb.scheduler import TaskScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
log = logging.getLogger("radar_kb.main")


def _run_discover() -> None:
    TaskScheduler(load_kb_settings(), "discover").run_forever()


def _run_content() -> None:
    TaskScheduler(load_kb_settings(), "content").run_forever()


def main(argv: list[str] | None = None) -> None:
    """
    启动 radar_kb 调度器。

    Args:
        argv: 子命令 discover | content | all
    """
    args = list(sys.argv if argv is None else argv)
    mode = (args[1] if len(args) > 1 else "all").strip().lower()
    if mode == "discover":
        _run_discover()
        return
    if mode == "content":
        _run_content()
        return
    if mode == "all":
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
    raise SystemExit(f"未知模式: {mode!r}，请使用 discover | content | all")


if __name__ == "__main__":
    main()
