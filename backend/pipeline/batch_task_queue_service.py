"""
批次任务（batch_task）内存队列服务
支持按 job_id 入队、消费者调用 BatchTaskExecuteService.run_one_batch_task(session_factory, item)。
设计文档：cursor_docs/022803-批次任务执行模版与队列对接技术设计.md、030203-批次任务执行Session拆分改造技术方案.md
"""
from __future__ import annotations

import asyncio
import logging
from typing import Set

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.batch.batch_task_execute_service import BatchTaskExecuteService
from backend.domain.batch.dto import BatchTaskQueueItem
from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.repository.batch.batch_job_repository import (
    BatchJobRepository,
)
from backend.infrastructure.database.repository.batch.batch_task_repository import (
    BatchTaskRepository,
    STATUS_PENDING,
)

logger = logging.getLogger(__name__)

_queue: asyncio.Queue | None = None
_in_flight_ids: Set[str] | None = None
_CONSUMER_COUNT = 4


def _ensure_queue() -> None:
    """确保队列与 in_flight_ids 已初始化。"""
    global _queue, _in_flight_ids
    if _queue is None:
        _queue = asyncio.Queue()
        _in_flight_ids = set()


async def enqueue_task_by_id(task_id: str, session: AsyncSession) -> int:
    """
    根据 task_id 查询 task（含 job_type 需从 job 取），构造 BatchTaskQueueItem 入队。
    设计文档：cursor_docs/030204-Step03-1任务子界面类数据清洗能力技术设计.md
    返回 1 表示入队成功，0 表示 task 不存在或入队失败。
    """
    _ensure_queue()
    task_id = (task_id or "").strip()
    if not task_id:
        return 0
    task_repo = BatchTaskRepository(session)
    task = await task_repo.get_by_id(task_id)
    if not task:
        return 0
    job_repo = BatchJobRepository(session)
    job = await job_repo.get_by_id(task.job_id or "")
    job_type = (job.job_type or "") if job else ""
    item = BatchTaskQueueItem(
        job_type=job_type,
        task_id=task.id,
        task_version=getattr(task, "version", 0) or 0,
    )
    _in_flight_ids.add(task.id)
    _queue.put_nowait(item)
    return 1


async def enqueue_batch_by_job_id(job_id: str, session: AsyncSession) -> int:
    """
    将指定批次（job_id 为 BatchJobRecord.id）下 status=pending 的 batch_task 入队。
    入队时构造 BatchTaskQueueItem（job_type、task_id、task_version）。
    返回本次入队数量。
    """
    _ensure_queue()
    job_repo = BatchJobRepository(session)
    job = await job_repo.get_by_id(job_id)
    if not job:
        return 0
    task_repo = BatchTaskRepository(session)
    tasks = await task_repo.get_list(
        job_id=job_id,
        status=STATUS_PENDING,
        limit=10000,
    )
    added = 0
    for task in tasks:
        if task.id in _in_flight_ids:
            continue
        item = BatchTaskQueueItem(
            job_type=job.job_type or "",
            task_id=task.id,
            task_version=getattr(task, "version", 0) or 0,
        )
        _in_flight_ids.add(task.id)
        _queue.put_nowait(item)
        added += 1
    return added


def get_queue_stats() -> dict:
    """返回 queue_size 与 in_flight_count。"""
    _ensure_queue()
    return {
        "queue_size": _queue.qsize(),
        "in_flight_count": len(_in_flight_ids),
    }


def clear_all_queue() -> int:
    """
    清空队列中所有任务，返回移除数量。正在执行中的任务不中断。
    设计文档：cursor_docs/030202-批次任务batch_jobs与Step02清洗批次管理功能对比与缺口分析.md
    """
    _ensure_queue()
    n = 0
    while True:
        try:
            item: BatchTaskQueueItem = _queue.get_nowait()
            _in_flight_ids.discard(item.task_id)
            n += 1
        except asyncio.QueueEmpty:
            break
    return n


async def remove_batch_by_job_id(job_id: str, session: AsyncSession) -> int:
    """
    从队列中移除指定 job 下的所有任务（仅尚未被消费的），返回移除数量。
    设计文档：cursor_docs/030202。
    """
    _ensure_queue()
    task_repo = BatchTaskRepository(session)
    tasks = await task_repo.get_list(job_id=job_id, limit=100000)
    job_task_ids = {t.id for t in tasks}
    if not job_task_ids:
        return 0
    to_put_back: list[BatchTaskQueueItem] = []
    n = 0
    while True:
        try:
            item = _queue.get_nowait()
            if item.task_id in job_task_ids:
                _in_flight_ids.discard(item.task_id)
                n += 1
            else:
                to_put_back.append(item)
        except asyncio.QueueEmpty:
            break
    for item in to_put_back:
        _queue.put_nowait(item)
    return n


async def _consumer_loop() -> None:
    """
    单消费者协程：取 BatchTaskQueueItem → 调用 run_one_batch_task(session_factory, item)。
    模版内部使用两段短 session（加载/乐观锁、业务、回写），不再为单次执行持长 session。设计文档：030203。
    """
    _ensure_queue()
    session_factory = get_session_factory()
    execute_service = BatchTaskExecuteService()
    while True:
        item: BatchTaskQueueItem = await _queue.get()
        try:
            await execute_service.run_one_batch_task(session_factory, item)
        except Exception as e:
            logger.exception(
                "批次任务消费者执行失败 task_id=%s: %s",
                item.task_id,
                e,
            )
        finally:
            _in_flight_ids.discard(item.task_id)


def start_consumers() -> list[asyncio.Task]:
    """启动 N 个消费者协程，应在应用 lifespan 中只调用一次。返回任务列表供关闭时 cancel。"""
    _ensure_queue()
    tasks = [asyncio.create_task(_consumer_loop()) for _ in range(_CONSUMER_COUNT)]
    logger.info("BatchTask 队列消费者已启动，数量=%d", _CONSUMER_COUNT)
    return tasks
