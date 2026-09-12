"""
采集 Worker 注册表。

以后新增任务类型：在 WORKERS 里加一项即可，默认启动命令会全部拉起。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List


@dataclass(frozen=True)
class WorkerSpec:
    """单个后台 Worker 的描述。"""

    name: str
    description: str
    target: Callable[[], None]


def _run_crawl() -> None:
    from radar_crawl.workers.crawl_worker import main as crawl_main

    crawl_main()


def _run_pdf() -> None:
    from radar_crawl.workers.pdf_fill_worker import main as pdf_main

    pdf_main()


# 默认全部启动；新增 Worker 只往这里追加
WORKERS: List[WorkerSpec] = [
    WorkerSpec(
        name="crawl",
        description="阶段 A：抢 radar_crawl_task，巨潮列表入库",
        target=_run_crawl,
    ),
    WorkerSpec(
        name="pdf",
        description="阶段 B：抢无正文文档，PDF 抽字回填",
        target=_run_pdf,
    ),
]


def worker_names() -> List[str]:
    """已注册 Worker 名称列表。"""
    return [w.name for w in WORKERS]


def get_worker_map() -> Dict[str, WorkerSpec]:
    """name → WorkerSpec。"""
    return {w.name: w for w in WORKERS}
