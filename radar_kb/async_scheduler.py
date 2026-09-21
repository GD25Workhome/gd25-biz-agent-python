"""
跨站并发调度内核：DiscoverPool + ContentPool + SiteGate。

设计文档：ai_docs/26092102-列表正文跨站并发同站串行设计.md

相对旧 TaskScheduler：
  - 单一长期 asyncio 事件循环（禁止每任务 asyncio.run）
  - 列表 / 正文有界并发；同站经 SiteGate 串行 + 冷却
  - 默认软优先（有发现积压时正文槽位降为 content_low_concurrency）
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional, Set

from radar_kb import repository as repo
from radar_kb.config import KbSettings
from radar_kb.embed import embed_full_document_async, embed_stub_document_async
from radar_kb.registry import CONTENT_REGISTRY, DISCOVER_REGISTRY
from radar_kb.scheduler import SchedulerMode
from radar_kb.site_gate import (
    SiteGate,
    host_from_task,
    reset_shared_site_gate,
    set_shared_site_gate,
)
from radar_kb.types import ContentResult, DiscoverResult

log = logging.getLogger("radar_kb.concurrent")


class ConcurrentScheduler:
    """列表 / 正文跨站并发调度器。"""

    def __init__(self, settings: KbSettings, mode: SchedulerMode) -> None:
        self.settings = settings
        self.mode = mode
        self._gate = SiteGate(
            gap_min_sec=settings.site_gap_min_sec,
            gap_max_sec=settings.site_gap_max_sec,
            aging_after_discover=settings.site_gate_aging_after_discover,
        )
        self._discover_running = 0
        self._content_running = 0
        self._discover_sources: Set[str] = set()
        self._content_hosts: Set[str] = set()
        self._counter_lock = asyncio.Lock()
        self._stop_event = None
        self._embed_sem: Optional[asyncio.Semaphore] = None
        self._discover_sem: Optional[asyncio.Semaphore] = None
        self._content_sem: Optional[asyncio.Semaphore] = None
        self._discover_empty_until = 0.0
        self._content_empty_until = 0.0

    def run_forever(self, stop_event=None) -> None:
        """
            在当前线程跑长期 asyncio 主循环（供 daemon 线程调用）。

            Args:
                stop_event: 可选 threading.Event
        """
        self._stop_event = stop_event
        log.info(
            "并发调度启动 mode=%s worker=%s N_d=%s N_c=%s N_c_low=%s gap=%.1f~%.1fs",
            self.mode,
            self.settings.worker_id,
            self.settings.discover_max_concurrency,
            self.settings.content_max_concurrency,
            self.settings.content_low_concurrency,
            self.settings.site_gap_min_sec,
            self.settings.site_gap_max_sec,
        )
        try:
            asyncio.run(self._amain())
        finally:
            reset_shared_site_gate()
            log.info("并发调度退出 mode=%s", self.mode)

    def _stopped(self) -> bool:
        return bool(self._stop_event is not None and self._stop_event.is_set())

    async def _amain(self) -> None:
        """主协程：挂闸门、起双池监督协程。"""
        # 1. 绑定进程闸门（列表/正文 HTTP 注入点读取）
        set_shared_site_gate(self._gate)
        self._embed_sem = asyncio.Semaphore(
            max(1, int(self.settings.embed_max_concurrency))
        )
        self._discover_sem = asyncio.Semaphore(
            max(1, int(self.settings.discover_max_concurrency))
        )
        # content_sem 按「满额」创建；实际接活前再看软优先
        self._content_sem = asyncio.Semaphore(
            max(1, int(self.settings.content_max_concurrency))
        )

        workers: list[asyncio.Task] = []
        if self.mode in ("discover", "unified"):
            workers.append(asyncio.create_task(self._discover_loop(), name="discover-loop"))
        if self.mode in ("content", "unified"):
            workers.append(asyncio.create_task(self._content_loop(), name="content-loop"))

        try:
            while not self._stopped():
                await asyncio.sleep(0.5)
                # 任一路崩溃则记录并重启
                for i, t in enumerate(list(workers)):
                    if t.done():
                        exc = t.exception() if not t.cancelled() else None
                        if exc:
                            log.exception("调度子循环异常: %s", exc, exc_info=exc)
                        name = t.get_name()
                        if name == "discover-loop" and self.mode in (
                            "discover",
                            "unified",
                        ):
                            workers[i] = asyncio.create_task(
                                self._discover_loop(), name="discover-loop"
                            )
                        elif name == "content-loop" and self.mode in (
                            "content",
                            "unified",
                        ):
                            workers[i] = asyncio.create_task(
                                self._content_loop(), name="content-loop"
                            )
        finally:
            for t in workers:
                t.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    async def _soft_priority_blocks_content(self) -> bool:
        """
            软优先：发现正在跑或仍有 PENDING 时，正文有效槽位降为 N_c_low。

            Returns:
                True 表示当前不应再接新的正文（已达 low 上限）
        """
        low = max(0, int(self.settings.content_low_concurrency))
        full = max(1, int(self.settings.content_max_concurrency))
        if low >= full:
            return False

        async with self._counter_lock:
            running = self._discover_running
        if running > 0:
            async with self._counter_lock:
                return self._content_running >= low

        # 查 PENDING（不含 RUNNING，避免「历史失败」误伤）
        def _peek() -> int:
            conn = repo.connect(self.settings)
            try:
                total = 0
                for kind in DISCOVER_REGISTRY:
                    total += repo.count_pending_crawl_tasks(
                        conn, self.settings, kind
                    )
                return total
            finally:
                conn.close()

        pending = await asyncio.to_thread(_peek)
        if pending <= 0:
            return False
        async with self._counter_lock:
            return self._content_running >= low

    async def _discover_loop(self) -> None:
        """发现监督循环：填满 N_d 槽位。"""
        assert self._discover_sem is not None
        inflight: set[asyncio.Task] = set()
        while not self._stopped():
            now = time.monotonic()
            if now < self._discover_empty_until and not inflight:
                await asyncio.sleep(min(1.0, self._discover_empty_until - now))
                continue

            # 回收已完成
            done = {t for t in inflight if t.done()}
            for t in done:
                inflight.discard(t)
                try:
                    t.result()
                except Exception:
                    log.exception("发现任务异常")

            free = max(0, int(self.settings.discover_max_concurrency) - len(inflight))
            if free <= 0:
                await asyncio.sleep(0.2)
                continue

            async with self._counter_lock:
                exclude = set(self._discover_sources)

            batch = await asyncio.to_thread(self._claim_discover_batch, free, exclude)
            if not batch:
                if not inflight:
                    self._discover_empty_until = (
                        time.monotonic() + float(self.settings.empty_backoff_sec)
                    )
                    log.info(
                        "发现表空，%.0fs 内少查",
                        self.settings.empty_backoff_sec,
                    )
                await asyncio.sleep(float(self.settings.poll_after_discover_sec))
                continue

            self._discover_empty_until = 0.0
            for task in batch:
                t = asyncio.create_task(
                    self._run_discover_one(task),
                    name=f"discover-{task.get('id')}",
                )
                inflight.add(t)
            await asyncio.sleep(0.05)

    def _claim_discover_batch(
        self, limit: int, exclude: set[str]
    ) -> list[dict[str, Any]]:
        """同步：按 kind 轮询批量认领（同源去重）。"""
        conn = repo.connect(self.settings)
        out: list[dict[str, Any]] = []
        try:
            per_kind = max(1, limit)
            for kind in DISCOVER_REGISTRY:
                if len(out) >= limit:
                    break
                locked_by = f"py-discover-{kind}-{self.settings.worker_id}"
                part = repo.claim_crawl_tasks_batch(
                    conn,
                    self.settings,
                    kind,
                    locked_by,
                    limit=min(per_kind, limit - len(out)),
                    exclude_source_keys=exclude | {
                        repo.source_key_from_crawl_task(t) for t in out
                    },
                )
                out.extend(part)
            return out
        finally:
            conn.close()

    async def _run_discover_one(self, task: dict[str, Any]) -> None:
        """执行一条发现任务（占 discover 槽 + 源键）。"""
        assert self._discover_sem is not None
        kind = str(task.get("source_kind") or "news_html")
        locked_by = f"py-discover-{kind}-{self.settings.worker_id}"
        sk = repo.source_key_from_crawl_task(task)
        async with self._discover_sem:
            async with self._counter_lock:
                self._discover_running += 1
                self._discover_sources.add(sk)
            try:
                await self._execute_discover(task, kind, locked_by)
            finally:
                async with self._counter_lock:
                    self._discover_running = max(0, self._discover_running - 1)
                    self._discover_sources.discard(sk)

    async def _execute_discover(
        self, task: dict[str, Any], kind: str, locked_by: str
    ) -> None:
        """发现：执行器 + 写库 + stub embed。"""
        entry = DISCOVER_REGISTRY.get(kind)
        if entry is None:
            log.warning("未知发现 kind=%s", kind)
            return
        executor = entry[2](self.settings)
        task_id = int(task["id"])

        def _fail(exc: BaseException) -> None:
            conn = repo.connect(self.settings)
            try:
                repo.finish_crawl_task(
                    conn,
                    task_id,
                    worker_id=locked_by,
                    success=False,
                    stats={"error": str(exc)[:200]},
                    error_message=str(exc),
                    task=task,
                )
            finally:
                conn.close()

        try:
            if hasattr(executor, "execute_async"):
                result: DiscoverResult = await executor.execute_async(
                    task, site_gate=self._gate
                )
            else:
                # cninfo 等同步执行器
                result = await asyncio.to_thread(executor.execute, task)

            def _post() -> tuple[int, list]:
                conn = repo.connect(self.settings)
                try:
                    return repo.discover_post_success(conn, task, result, locked_by)
                finally:
                    conn.close()

            upserted, written = await asyncio.to_thread(_post)
            assert self._embed_sem is not None
            for doc_id, item in written:
                async with self._embed_sem:
                    await embed_stub_document_async(
                        document_id=doc_id,
                        company_id=int(task["company_id"]),
                        title=item.title,
                        summary=item.content_summary,
                        url=item.news_url,
                        source_kind=kind,
                        worker_id=locked_by,
                    )

            def _ok() -> None:
                conn = repo.connect(self.settings)
                try:
                    repo.finish_crawl_task(
                        conn,
                        task_id,
                        worker_id=locked_by,
                        success=True,
                        stats=result.stats,
                        news_url_count=upserted,
                        cost_ms=result.cost_ms,
                        stop_reason=result.stop_reason,
                        agent_trace_id=result.agent_trace_id,
                        task=task,
                    )
                finally:
                    conn.close()

            await asyncio.to_thread(_ok)
            log.info(
                "发现成功 task_id=%s kind=%s upserted=%s",
                task_id,
                kind,
                upserted,
            )
        except Exception as exc:
            log.exception("发现失败 task_id=%s kind=%s", task_id, kind)
            await asyncio.to_thread(_fail, exc)

    async def _content_loop(self) -> None:
        """正文监督循环：软优先 + 跨站打散认领 + 有界并发。"""
        assert self._content_sem is not None
        inflight: set[asyncio.Task] = set()
        while not self._stopped():
            now = time.monotonic()
            if now < self._content_empty_until and not inflight:
                await asyncio.sleep(min(1.0, self._content_empty_until - now))
                continue

            done = {t for t in inflight if t.done()}
            for t in done:
                inflight.discard(t)
                try:
                    t.result()
                except Exception:
                    log.exception("正文任务异常")

            if await self._soft_priority_blocks_content():
                await asyncio.sleep(0.3)
                continue

            free = max(
                0, int(self.settings.content_max_concurrency) - len(inflight)
            )
            # 软优先时进一步限制本轮 spawn
            low = max(0, int(self.settings.content_low_concurrency))
            async with self._counter_lock:
                d_run = self._discover_running
            if d_run > 0 or await self._has_pending_discover():
                free = min(free, max(0, low - len(inflight)))

            if free <= 0:
                await asyncio.sleep(0.2)
                continue

            async with self._counter_lock:
                busy_hosts = set(self._content_hosts)

            batch = await asyncio.to_thread(
                self._claim_content_batch, free, busy_hosts
            )
            if not batch:
                if not inflight:
                    self._content_empty_until = (
                        time.monotonic() + float(self.settings.empty_backoff_sec)
                    )
                    log.info(
                        "正文表空，%.0fs 内少查",
                        self.settings.empty_backoff_sec,
                    )
                await asyncio.sleep(
                    min(float(self.settings.poll_after_content_sec), 1.0)
                )
                continue

            self._content_empty_until = 0.0
            for task in batch:
                host = host_from_task(task) or "__global__"
                # 未到点则短暂等待，仍占 inflight 但先 await gate ready 再占 sem
                t = asyncio.create_task(
                    self._run_content_one(task, host),
                    name=f"content-{task.get('id')}",
                )
                inflight.add(t)
            await asyncio.sleep(0.05)

    async def _has_pending_discover(self) -> bool:
        """是否存在 PENDING 发现（软优先）。"""

        def _peek() -> bool:
            conn = repo.connect(self.settings)
            try:
                for kind in DISCOVER_REGISTRY:
                    if repo.count_pending_crawl_tasks(conn, self.settings, kind) > 0:
                        return True
                return False
            finally:
                conn.close()

        return await asyncio.to_thread(_peek)

    def _claim_content_batch(
        self, limit: int, busy_hosts: set[str]
    ) -> list[dict[str, Any]]:
        """
            同步认领正文；跳过当前已在跑的 host（减少同站占槽）。
        """
        conn = repo.connect(self.settings)
        out: list[dict[str, Any]] = []
        try:
            repo.reset_stale_content_tasks(conn, 1800)
            repo.reset_stale_crawl_tasks(
                conn, int(self.settings.crawl_stale_timeout_sec)
            )
            batch_limit = max(limit * 3, limit)
            for kind, _entry in CONTENT_REGISTRY.items():
                if len(out) >= limit:
                    break
                locked_by = f"py-content-{kind}-{self.settings.worker_id}"
                part = repo.claim_content_tasks_batch(
                    conn,
                    self.settings,
                    kind,
                    locked_by,
                    limit=batch_limit,
                )
                for task in part:
                    if len(out) >= limit:
                        # 多领的放回 PENDING
                        repo.release_content_task_claim(
                            conn,
                            int(task["id"]),
                            worker_id=locked_by,
                        )
                        continue
                    host = host_from_task(task) or "__global__"
                    if host in busy_hosts or any(
                        host_from_task(t) == host for t in out
                    ):
                        repo.release_content_task_claim(
                            conn,
                            int(task["id"]),
                            worker_id=locked_by,
                        )
                        continue
                    # host 未到点也不在此阻塞；由 run 侧 wait
                    out.append(task)
                    busy_hosts.add(host)
            return out
        finally:
            conn.close()

    async def _run_content_one(self, task: dict[str, Any], host: str) -> None:
        """执行一条正文：先等 host 冷却（不占 sem），再占槽执行。"""
        assert self._content_sem is not None
        kind = str(task.get("source_kind") or "news_html")
        locked_by = f"py-content-{kind}-{self.settings.worker_id}"

        # 1. 锁外等到 SiteGate 冷却，避免占着池槽 sleep
        await self._gate.wait_until_ready(host)

        async with self._content_sem:
            async with self._counter_lock:
                self._content_running += 1
                self._content_hosts.add(host)
            try:
                await self._execute_content(task, kind, locked_by)
            finally:
                async with self._counter_lock:
                    self._content_running = max(0, self._content_running - 1)
                    self._content_hosts.discard(host)

    async def _execute_content(
        self, task: dict[str, Any], kind: str, locked_by: str
    ) -> None:
        """正文：执行器 + embed + finish。"""
        entry = CONTENT_REGISTRY.get(kind)
        task_id = int(task["id"])
        if entry is None:
            def _release() -> None:
                conn = repo.connect(self.settings)
                try:
                    repo.release_content_task_claim(
                        conn, task_id, worker_id=locked_by
                    )
                finally:
                    conn.close()

            await asyncio.to_thread(_release)
            return

        budget = entry[1]
        executor = entry[2](self.settings)
        max_attempts = int(budget.max_attempts)

        try:
            if hasattr(executor, "execute_async"):
                result: ContentResult = await executor.execute_async(
                    task, site_gate=self._gate
                )
            else:
                result = await asyncio.to_thread(executor.execute, task)

            if not result.content_text:
                err = (result.extra or {}).get("error") or "正文为空"

                def _fail_empty() -> None:
                    conn = repo.connect(self.settings)
                    try:
                        repo.finish_content_task_failure(
                            conn,
                            task,
                            worker_id=locked_by,
                            error_message=str(err),
                            actual_channel=result.actual_channel,
                            cost_ms=result.cost_ms,
                            agent_trace_id=result.agent_trace_id,
                            max_attempts=max_attempts,
                        )
                    finally:
                        conn.close()

                await asyncio.to_thread(_fail_empty)
                return

            def _load_doc() -> Optional[dict]:
                conn = repo.connect(self.settings)
                try:
                    return repo.get_document_by_news_url(
                        conn, int(task["news_url_id"])
                    )
                finally:
                    conn.close()

            doc = await asyncio.to_thread(_load_doc)
            if not doc:
                raise RuntimeError(
                    f"缺少 stub document news_url_id={task.get('news_url_id')}"
                )
            doc_id = int(doc["id"])
            url = (task.get("url") or doc.get("url") or "").strip()

            assert self._embed_sem is not None
            async with self._embed_sem:
                embed_status, embed_err = await embed_full_document_async(
                    document_id=doc_id,
                    company_id=int(task["company_id"]),
                    title=result.title,
                    content_text=result.content_text,
                    url=url,
                    source_kind=kind,
                    worker_id=locked_by,
                )
            if embed_err:
                log.warning(
                    "正文向量失败 task_id=%s document_id=%s err=%s",
                    task_id,
                    doc_id,
                    embed_err,
                )

            result_row = {
                "document_id": doc_id,
                "title": result.title,
                "published_at": result.published_at,
                "content_text": result.content_text,
                "content_summary": result.content_summary,
                "content_hash": result.content_hash,
                "actual_channel": result.actual_channel,
                "embed_status": embed_status,
                "cost_ms": result.cost_ms,
                "agent_trace_id": result.agent_trace_id,
            }

            def _ok() -> None:
                conn = repo.connect(self.settings)
                try:
                    repo.finish_content_task_success(
                        conn, task, result_row, locked_by
                    )
                finally:
                    conn.close()

            await asyncio.to_thread(_ok)
            log.info(
                "正文成功 task_id=%s kind=%s document_id=%s embed_status=%s",
                task_id,
                kind,
                doc_id,
                embed_status,
            )
        except Exception as exc:
            log.exception("正文失败 task_id=%s kind=%s", task_id, kind)

            def _fail() -> None:
                conn = repo.connect(self.settings)
                try:
                    repo.finish_content_task_failure(
                        conn,
                        task,
                        worker_id=locked_by,
                        error_message=str(exc),
                        actual_channel=None,
                        cost_ms=None,
                        agent_trace_id=None,
                        max_attempts=max_attempts,
                    )
                finally:
                    conn.close()

            await asyncio.to_thread(_fail)
