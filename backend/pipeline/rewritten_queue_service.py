"""
Step02 改写任务内存队列服务

支持按批次入队、单条入队、清空全部队列、按批次移除队列；多消费者协程消费队列并执行 run_one_rewritten。
设计文档：cursor_docs/021105-Step02批次任务队列与运行停止技术设计.md
"""
from __future__ import annotations

import asyncio
import logging
from typing import Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.repository.data_items_rewritten_repository import (
    DataItemsRewrittenRepository,
    STATUS_INIT,
)
from backend.pipeline.rewritten_service import _mark_failed, run_one_rewritten

logger = logging.getLogger(__name__)

# 队列元素为 (record_id: str, batch_code: str)
_queue: asyncio.Queue | None = None
_in_flight_ids: Set[str] | None = None
_CONSUMER_COUNT = 4


def _ensure_queue() -> None:
    """确保队列与 in_flight_ids 已初始化。"""
    global _queue, _in_flight_ids
    if _queue is None:
        _queue = asyncio.Queue()
        _in_flight_ids = set()


def is_in_flight(record_id: str) -> bool:
    """
    判断 record_id 是否已在队列或正在执行中（只读，不修改队列与 DB）。
    用于单条再次运行前先检查，避免先改 DB 为 init 再入队失败导致状态误修改。
    """
    _ensure_queue()
    return record_id in _in_flight_ids


async def enqueue_batch(batch_code: str, session: AsyncSession) -> int:
    """
    将指定批次下 status in (init, processing) 的记录入队，按 id 去重。
    对未在 _in_flight_ids 的每条记录：先将该条状态改为 init，再入队。
    返回本次入队数量。设计文档：021201。
    """
    _ensure_queue()
    repo = DataItemsRewrittenRepository(session)
    records = await repo.get_pending_by_batch_code(batch_code)
    added = 0
    for rec in records:
        rid = rec.id
        if rid in _in_flight_ids:
            continue
        await repo.update_status(rid, STATUS_INIT)
        _in_flight_ids.add(rid)
        _queue.put_nowait((rid, rec.batch_code or ""))
        added += 1
    return added


def enqueue_one(record_id: str, batch_code: str) -> bool:
    """
    单条入队（模式 3：再次运行）。
    若 record_id 已在 in_flight_ids 则返回 False；否则入队并返回 True。
    调用方负责先将该条 DB 状态改为 init。设计文档：021201。
    """
    _ensure_queue()
    if record_id in _in_flight_ids:
        return False
    _in_flight_ids.add(record_id)
    _queue.put_nowait((record_id, batch_code or ""))
    return True


def clear_all_queue() -> int:
    """模式 1：清空队列中所有任务，返回移除数量。正在执行的不中断。"""
    _ensure_queue()
    n = 0
    while True:
        try:
            record_id, _ = _queue.get_nowait()
            _in_flight_ids.discard(record_id)
            n += 1
        except asyncio.QueueEmpty:
            break
    return n


def remove_batch_from_queue(batch_code: str) -> int:
    """模式 2：从队列中移除当前批次的任务，返回移除数量。其他批次任务回填队列。"""
    _ensure_queue()
    to_put_back: list[Tuple[str, str]] = []
    n = 0
    while True:
        try:
            record_id, bc = _queue.get_nowait()
            if bc == batch_code:
                _in_flight_ids.discard(record_id)
                n += 1
            else:
                to_put_back.append((record_id, bc))
        except asyncio.QueueEmpty:
            break
    for item in to_put_back:
        _queue.put_nowait(item)
    return n


def get_queue_stats() -> dict:
    """返回 queue_size（排队数）与 in_flight_count（队列中+执行中的 id 总数）。"""
    _ensure_queue()
    return {
        "queue_size": _queue.qsize(),
        "in_flight_count": len(_in_flight_ids),
    }


async def _consumer_loop() -> None:
    """
    单消费者协程：取任务 → 查库 → 仅当 status=init 时更新为 processing 再执行。
    若 update_status_to_processing_if_init 未更新到行则跳过执行（防重）。设计文档：021201。
    """
    _ensure_queue()
    session_factory = get_session_factory()
    while True:
        record_id: str
        _batch_code: str
        record_id, _batch_code = await _queue.get()
        try:
            async with session_factory() as session:
                repo = DataItemsRewrittenRepository(session)
                rec = await repo.get_by_id(record_id)
            if not rec:
                await _mark_failed(record_id, "记录不存在")
            else:
                async with session_factory() as session:
                    repo = DataItemsRewrittenRepository(session)
                    ok = await repo.update_status_to_processing_if_init(record_id)
                    await session.commit()
                if not ok:
                    logger.info(
                        "跳过重复消费 record_id=%s（状态非 init 或已被占位）",
                        record_id,
                    )
                else:
                    await run_one_rewritten(rec)
        except Exception as e:
            logger.exception("消费者执行失败 record_id=%s: %s", record_id, e)
            await _mark_failed(record_id, str(e))
        finally:
            _in_flight_ids.discard(record_id)


def start_consumers() -> list[asyncio.Task]:
    """启动 N 个消费者协程，应在应用 lifespan 中只调用一次。返回任务列表供关闭时 cancel。"""
    _ensure_queue()
    tasks = [asyncio.create_task(_consumer_loop()) for _ in range(_CONSUMER_COUNT)]
    logger.info("Rewritten 队列消费者已启动，数量=%d", _CONSUMER_COUNT)
    return tasks
