"""
雷达新闻知识库写入 worker 主循环（脚本 CLI 与 FastAPI lifespan 共用）。

    拉模型：扫 exhibition MySQL PENDING → 抢锁 → 串行 process_task。
    不改为 Rewritten 式内存队列；入队仍由 Java 建 task。

设计文档：ai_docs/26091602 / 26091604；方案 A′：lifespan 挂起本循环。
"""
from __future__ import annotations

import asyncio
import logging
import signal
import time
from dataclasses import dataclass
from typing import Optional

from backend.app.config import settings
from backend.domain.news_content import repository as repo
from backend.domain.news_content.content_fetcher import close_http_client
from backend.domain.news_content.pipeline import NewsContentProcessor
from backend.infrastructure.database.mysql_connection import (
    close_pool,
    default_worker_id,
)

logger = logging.getLogger("news-content-worker")

# RUNNING 超时重置的检查间隔（秒）：与锁超时同量级即可，不必每轮都扫
_STALE_CHECK_INTERVAL_SECONDS = 60.0

# FastAPI 关闭时等待当前任务收尾的上限（秒）；超时再 cancel，避免拖死滚动发布
_IN_APP_SHUTDOWN_WAIT_SECONDS = 300.0


@dataclass
class NewsContentWorkerOptions:
    """
        worker 主循环运行参数（CLI 与 lifespan 共用）。

        Attributes:
            batch_size: 每轮领取条数；None 用配置默认
            poll_interval: 无任务休眠秒数；None 用配置默认
            worker_id: locked_by 标识；None 时配置或 hostname:pid
            skip_backfill: 是否跳过 embedding 补跑
            once: 只处理一轮（claim 一批）后退出
            max_tasks: 处理满 N 条后退出；0 表示不限
            disable_agent: 本次禁用 Agent 兜底
            close_pool_on_exit: 退出时是否关闭 exhibition MySQL 连接池
            install_signals: 是否注册 SIGINT/SIGTERM（仅独立 CLI；lifespan 勿开）
    """

    batch_size: Optional[int] = None
    poll_interval: Optional[float] = None
    worker_id: Optional[str] = None
    skip_backfill: bool = False
    once: bool = False
    max_tasks: int = 0
    disable_agent: bool = False
    close_pool_on_exit: bool = True
    install_signals: bool = False


async def sleep_or_stop(stop: asyncio.Event, seconds: float) -> bool:
    """
        可被 stop 打断的 sleep。

        Args:
            stop: 停机事件
            seconds: 最长休眠秒数

        Returns:
            True 表示已收到停止信号（调用方应退出循环）
    """
    if seconds <= 0:
        return stop.is_set()
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
        return True
    except asyncio.TimeoutError:
        return False


def install_signal_handlers(stop: asyncio.Event) -> None:
    """
        注册 SIGINT/SIGTERM：置位 stop，当前任务处理完后再退出。

        仅独立脚本进程使用；挂在 FastAPI 内时由 uvicorn lifespan 关停，勿重复注册。
    """
    loop = asyncio.get_running_loop()

    def _on_signal(signum: int) -> None:
        logger.warning("收到信号 %s，准备优雅退出（当前任务处理完后停止）", signum)
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal, sig)
        except (NotImplementedError, RuntimeError):
            try:
                signal.signal(sig, lambda s, _f: _on_signal(s))
            except Exception:
                logger.debug("信号 %s 注册失败", sig, exc_info=True)


async def run_news_content_loop(
    stop: asyncio.Event,
    options: Optional[NewsContentWorkerOptions] = None,
) -> int:
    """
        新闻知识库写入主循环（扫表抢锁 + 串行处理）。

        Args:
            stop: 外部停机事件；置位后不再领取新任务，本轮剩余 RUNNING 靠锁超时回收
            options: 运行参数；None 则用配置默认值（适合 lifespan）

        Returns:
            进程/任务退出码（0 正常）
    """
    opts = options or NewsContentWorkerOptions()
    batch_size = int(opts.batch_size or settings.NEWS_CONTENT_BATCH_SIZE)
    poll_interval = float(
        opts.poll_interval
        if opts.poll_interval is not None
        else settings.NEWS_CONTENT_POLL_INTERVAL_SECONDS
    )
    worker_id = opts.worker_id or settings.NEWS_CONTENT_WORKER_ID or default_worker_id()

    # 1. 可选：本次禁用 Agent（CLI --no-agent）
    if opts.disable_agent:
        settings.NEWS_CONTENT_AGENT_FALLBACK_ENABLED = False

    # 2. 独立进程才接管信号；lifespan 场景由应用关闭路径 stop.set()
    if opts.install_signals:
        install_signal_handlers(stop)

    processor = NewsContentProcessor(worker_id=worker_id)

    logger.info(
        "worker 启动 id=%s db=%s@%s/%s collection=%s batch=%d poll=%.1fs "
        "lock_timeout=%ds agent_fallback=%s backfill=%s once=%s",
        worker_id,
        settings.EXHIBITION_MYSQL_USER,
        settings.EXHIBITION_MYSQL_HOST,
        settings.EXHIBITION_MYSQL_DB,
        settings.MILVUS_COLLECTION,
        batch_size,
        poll_interval,
        settings.NEWS_CONTENT_LOCK_TIMEOUT_SECONDS,
        settings.NEWS_CONTENT_AGENT_FALLBACK_ENABLED,
        not opts.skip_backfill,
        opts.once,
    )

    processed = 0
    last_stale_check = 0.0
    last_backfill = 0.0

    try:
        while not stop.is_set():
            now = time.monotonic()

            # ---- 1. RUNNING 超时重置（worker 挂死自愈） ----
            if now - last_stale_check >= _STALE_CHECK_INTERVAL_SECONDS:
                last_stale_check = now
                try:
                    reset = await repo.reset_stale_running(
                        settings.NEWS_CONTENT_LOCK_TIMEOUT_SECONDS
                    )
                    if reset:
                        logger.warning("RUNNING 超时重置回 PENDING：%d 条", reset)
                except Exception:
                    logger.exception("RUNNING 超时重置失败（下一轮重试）")

            # ---- 2. embedding 补跑循环 ----
            if (
                not opts.skip_backfill
                and now - last_backfill
                >= settings.NEWS_CONTENT_EMBED_BACKFILL_INTERVAL_SECONDS
            ):
                last_backfill = now
                try:
                    await processor.backfill_embeddings()
                except Exception:
                    logger.exception("补跑循环异常（不中断主循环）")

            # ---- 3. 抢一批任务 ----
            try:
                tasks = await repo.claim_tasks(worker_id, batch_size)
            except Exception:
                logger.exception("抢锁失败，休眠后重试")
                if await sleep_or_stop(stop, poll_interval):
                    break
                continue

            if not tasks:
                if await sleep_or_stop(stop, poll_interval):
                    break
                continue

            # ---- 4. 逐条串行处理 ----
            for index, task in enumerate(tasks):
                if stop.is_set():
                    remaining = len(tasks) - index
                    logger.warning(
                        "收到退出信号，本轮剩余 %d 条仍为 RUNNING，"
                        "将由锁超时（%ds）自动重置回 PENDING",
                        remaining,
                        settings.NEWS_CONTENT_LOCK_TIMEOUT_SECONDS,
                    )
                    break
                try:
                    outcome = await processor.process_task(task)
                    processed += 1
                    logger.info(
                        "任务处理完毕 task_id=%s ok=%s channel=%s document_id=%s "
                        "embed_status=%s cost_ms=%s error=%s",
                        outcome.task_id,
                        outcome.ok,
                        outcome.channel,
                        outcome.document_id,
                        outcome.embed_status,
                        outcome.cost_ms,
                        outcome.error,
                    )
                except Exception:
                    logger.exception(
                        "任务处理异常 task_id=%s（已跳过，等待超时重置）",
                        task.get("id"),
                    )

                if opts.max_tasks and processed >= opts.max_tasks:
                    logger.info("已达 max_tasks=%d，退出", opts.max_tasks)
                    stop.set()
                    break

            if opts.once:
                logger.info("once：完成一轮处理后退出")
                break
    finally:
        # 5. 收尾：处理器、HTTP 客户端、可选关连接池
        logger.info("worker 收尾：已处理 %d 条任务", processed)
        try:
            await processor.aclose()
        except Exception:
            logger.debug("processor 收尾异常", exc_info=True)
        try:
            await close_http_client()
        except Exception:
            logger.debug("http client 收尾异常", exc_info=True)
        if opts.close_pool_on_exit:
            close_pool()

    return 0


def start_news_content_worker_in_app() -> tuple[asyncio.Event, asyncio.Task]:
    """
        在 FastAPI lifespan 内拉起新闻知识库 worker 协程。

        Returns:
            (stop_event, task)：关闭时先 stop.set()，再 await task
    """
    stop = asyncio.Event()
    options = NewsContentWorkerOptions(
        install_signals=False,
        close_pool_on_exit=True,
    )
    task = asyncio.create_task(
        run_news_content_loop(stop, options),
        name="news-content-worker",
    )
    logger.info("新闻知识库 worker 已在应用内启动（NEWS_CONTENT_WORKER_IN_APP）")
    return stop, task


async def stop_news_content_worker_in_app(
    stop: asyncio.Event,
    task: asyncio.Task,
    *,
    wait_seconds: float = _IN_APP_SHUTDOWN_WAIT_SECONDS,
) -> None:
    """
        优雅停止应用内 worker：置位 stop，等待当前任务收尾。

        Args:
            stop: 与 start 时同一事件
            task: 与 start 时同一 Task
            wait_seconds: 最长等待；超时则 cancel
    """
    stop.set()
    try:
        await asyncio.wait_for(task, timeout=wait_seconds)
        logger.info("新闻知识库 worker 已优雅停止")
    except asyncio.TimeoutError:
        logger.warning(
            "新闻知识库 worker 在 %.0fs 内未退出，强制 cancel", wait_seconds
        )
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("停止新闻知识库 worker 时异常")
