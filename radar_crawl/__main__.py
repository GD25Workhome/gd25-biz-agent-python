"""
雷达采集统一入口：默认一个命令启动全部 Worker。

用法（仓库根目录）：
    python -m radar_crawl              # 启动注册表里全部任务（推荐）
    python -m radar_crawl crawl        # 仅调试：只跑某一个
    python -m radar_crawl pdf

环境变量：
    RADAR_WORKER_MODE=all|crawl|pdf|...
    未设置时默认为 all
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from multiprocessing import Process
from typing import List

from radar_crawl.registry import WORKERS, get_worker_map, worker_names

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
log = logging.getLogger("radar.main")


def _resolve_mode(argv: list[str]) -> str:
    """命令行优先，其次环境变量，默认 all（一键全开）。"""
    if len(argv) > 1 and argv[1].strip():
        return argv[1].strip().lower()
    return (os.getenv("RADAR_WORKER_MODE") or "all").strip().lower()


def _start_workers(names: List[str]) -> List[Process]:
    """按名称启动子进程。"""
    mapping = get_worker_map()
    processes: List[Process] = []
    for name in names:
        spec = mapping[name]
        proc = Process(target=spec.target, name=f"radar-{name}", daemon=False)
        proc.start()
        log.info("已启动 Worker name=%s pid=%s desc=%s", name, proc.pid, spec.description)
        processes.append(proc)
    return processes


def _shutdown(processes: List[Process]) -> None:
    """优雅结束子进程。"""
    log.info("正在停止 %s 个 Worker ...", len(processes))
    for proc in processes:
        if proc.is_alive():
            proc.terminate()
    for proc in processes:
        proc.join(timeout=15)
        if proc.is_alive():
            log.warning("强制结束 Worker name=%s pid=%s", proc.name, proc.pid)
            proc.kill()
            proc.join(timeout=5)


def _supervise(processes: List[Process]) -> None:
    """
        主进程常驻监督：任一子进程异常退出则结束全部（交给 K8s 重启）。
    """
    stop = {"flag": False}

    def _on_signal(signum: int, _frame: object) -> None:
        log.info("收到信号 %s，准备退出", signum)
        stop["flag"] = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    try:
        while not stop["flag"]:
            for proc in processes:
                if not proc.is_alive():
                    code = proc.exitcode
                    log.error(
                        "Worker 异常退出 name=%s pid=%s exitcode=%s，将停止全部 Worker",
                        proc.name,
                        proc.pid,
                        code,
                    )
                    stop["flag"] = True
                    break
            else:
                time.sleep(1.0)
                continue
            break
    finally:
        _shutdown(processes)


def main(argv: list[str] | None = None) -> None:
    """
        启动采集服务。

        默认 all：注册表内全部 Worker 各起一个子进程。
        传单个 name 时仅启动该 Worker（便于排障）。
    """
    args = list(sys.argv if argv is None else argv)
    mode = _resolve_mode(args)
    known = worker_names()
    aliases = {
        "all": known,
        "both": known,
        "a": ["crawl"],
        "list": ["crawl"],
        "b": ["pdf"],
        "fill": ["pdf"],
    }

    if mode in aliases:
        selected = aliases[mode]
    elif mode in known:
        selected = [mode]
    else:
        raise SystemExit(
            f"未知模式: {mode!r}。默认请直接: python -m radar_crawl\n"
            f"可选: all | {' | '.join(known)}"
        )

    log.info("启动采集服务 mode=%s workers=%s", mode, selected)
    processes = _start_workers(selected)

    if len(processes) == 1:
        # 单 Worker：直接 join，子进程即业务循环
        try:
            processes[0].join()
        except KeyboardInterrupt:
            _shutdown(processes)
        return

    _supervise(processes)


if __name__ == "__main__":
    main()
