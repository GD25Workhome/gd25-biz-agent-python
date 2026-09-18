"""
TaskScheduler：统一单 loop（发现优先）或独立 discover/content 循环。

统一模式节奏：
  - 本轮跑过发现 → 短休，立刻再抢发现（尽快清空积压）
  - 本轮跑过正文 → 长休（正文更耗出网/LLM）
  - 查表为空 → 该类进入空表步长（默认 60s 内不再查）
  - 步长未到 → 跳过该类查表；两路都不可查时睡到最近 next_at
  - 正文让路（他机发现中）→ 短延迟重试，不走空表 1min
"""
from __future__ import annotations

import logging
import time
from typing import Literal

from radar_kb import repository as repo
from radar_kb.config import KbSettings
from radar_kb.content_frontier import ContentFrontier, PoliteKeyMode
from radar_kb.embed import embed_full_document, embed_stub_document
from radar_kb.registry import CONTENT_REGISTRY, DISCOVER_REGISTRY
from radar_kb.types import ContentResult, DiscoverResult

log = logging.getLogger("radar_kb.scheduler")

SchedulerMode = Literal["discover", "content", "unified"]
WorkKind = Literal["discover", "content", "idle"]
# work=有活; empty=查了无任务; deferred=步长未到未查; yielded=让路未执行
PollOutcome = Literal["work", "empty", "deferred", "yielded"]


class TaskScheduler:
    """发现 / 正文 / 统一调度器。"""

    def __init__(self, settings: KbSettings, mode: SchedulerMode) -> None:
        self.settings = settings
        self.mode = mode
        # 单调时钟：到点前跳过对应表查询（空表步长）
        self._discover_next_at: float = 0.0
        self._content_next_at: float = 0.0
        polite_mode: PoliteKeyMode = "source_url_id"
        if settings.content_polite_key in ("source_url_id", "host", "company_id"):
            polite_mode = settings.content_polite_key  # type: ignore[assignment]
        self._content_frontier = ContentFrontier(
            polite_key_mode=polite_mode,
            same_key_gap_min_sec=settings.content_same_key_gap_min_sec,
            same_key_gap_max_sec=settings.content_same_key_gap_max_sec,
            site_min_interval_sec=settings.content_site_min_interval_sec,
        )

    def run_forever(self, stop_event=None) -> None:
        """
            主循环。

            Args:
                stop_event: 可选 threading.Event；置位后在本轮结束后退出
        """
        log.info(
            "调度器启动 mode=%s worker_id=%s "
            "after_discover=%.1fs after_content=%.1fs idle=%.1fs empty_backoff=%.1fs "
            "content_batch=%s polite_key=%s same_key_gap=%.1f~%.1fs",
            self.mode,
            self.settings.worker_id,
            self.settings.poll_after_discover_sec,
            self.settings.poll_after_content_sec,
            self.settings.poll_idle_sec,
            self.settings.empty_backoff_sec,
            self.settings.content_claim_batch,
            self.settings.content_polite_key,
            self.settings.content_same_key_gap_min_sec,
            self.settings.content_same_key_gap_max_sec,
        )
        while True:
            if stop_event is not None and stop_event.is_set():
                log.info("收到停止信号，退出 mode=%s", self.mode)
                break
            try:
                work = self._run_one_round()
            except KeyboardInterrupt:
                log.info("收到中断，退出 mode=%s", self.mode)
                break
            except Exception:
                log.exception("调度循环异常 mode=%s", self.mode)
                work = "idle"

            interval = self._rest_seconds(work)
            log.debug("本轮 work=%s，休息 %.1fs", work, interval)
            if self._interruptible_sleep(interval, stop_event):
                log.info("收到停止信号，退出 mode=%s", self.mode)
                break

    def _run_one_round(self) -> WorkKind:
        """
            执行一轮抢任务逻辑，返回本轮实际完成的工作类型。

            unified：发现到点则优先；发现有活则本轮不再跑正文。
        """
        now = time.monotonic()
        if self.mode == "discover":
            return "discover" if self._poll_discover(now) == "work" else "idle"
        if self.mode == "content":
            return "content" if self._poll_content(now) == "work" else "idle"

        # unified：发现优先（仅当步长允许查表时）
        if self._poll_discover(now) == "work":
            return "discover"
        if self._poll_content(now) == "work":
            return "content"
        return "idle"

    def _poll_discover(self, now: float) -> PollOutcome:
        """带空表步长的发现轮询。"""
        if now < self._discover_next_at:
            log.debug(
                "发现步长未到，跳过查表 remain=%.1fs",
                self._discover_next_at - now,
            )
            return "deferred"

        if self._discover_once():
            self._discover_next_at = 0.0
            return "work"

        backoff = float(self.settings.empty_backoff_sec)
        self._discover_next_at = now + backoff
        log.info("发现表空，%.0fs 内跳过查表", backoff)
        return "empty"

    def _poll_content(self, now: float) -> PollOutcome:
        """
            正文轮询：内存 Frontier 未空时可无视空表步长继续 pop。
        """
        # Frontier 仍有货：直接消费（含同站冷却等待）
        if not self._content_frontier.empty():
            outcome = self._content_once()
            if outcome == "work":
                self._content_next_at = 0.0
            elif outcome == "yielded":
                retry = float(self.settings.poll_after_discover_sec)
                self._content_next_at = now + max(retry, 0.5)
            return outcome

        if now < self._content_next_at:
            log.debug(
                "正文步长未到，跳过查表 remain=%.1fs",
                self._content_next_at - now,
            )
            return "deferred"

        outcome = self._content_once()
        if outcome == "work":
            self._content_next_at = 0.0
            return "work"

        if outcome == "yielded":
            retry = float(self.settings.poll_after_discover_sec)
            self._content_next_at = now + max(retry, 0.5)
            log.debug("正文让路，%.1fs 后再查", self._content_next_at - now)
            return "yielded"

        backoff = float(self.settings.empty_backoff_sec)
        self._content_next_at = now + backoff
        log.info("正文表空，%.0fs 内跳过查表", backoff)
        return "empty"

    def _rest_seconds(self, work: WorkKind) -> float:
        """按本轮工作类型选择休息时长；idle 时睡到最近的查表窗口。"""
        if work == "discover":
            return float(self.settings.poll_after_discover_sec)
        if work == "content":
            # Frontier 已按站冷却；轮间短休即可换站，避免再叠 10s 全局空等
            return min(float(self.settings.poll_after_content_sec), 1.0)
        return self._idle_sleep_seconds()

    def _idle_sleep_seconds(self) -> float:
        """
            两路皆无活时的休息：优先睡到更近的 next_at，避免空表后仍按 10s 空转。
        """
        now = time.monotonic()
        waits: list[float] = []
        if self._discover_next_at > now:
            waits.append(self._discover_next_at - now)
        if self._content_next_at > now:
            waits.append(self._content_next_at - now)
        if waits:
            # 至少 0.5s，避免紧循环；不超过 empty_backoff 作为上限保护
            return max(0.5, min(waits))
        return float(self.settings.poll_idle_sec)

    @staticmethod
    def _interruptible_sleep(interval: float, stop_event) -> bool:
        """
            分段 sleep；若 stop 置位则提前返回 True。

            Returns:
                True 表示应退出主循环
        """
        if interval <= 0:
            return bool(stop_event is not None and stop_event.is_set())
        slept = 0.0
        while slept < interval:
            if stop_event is not None and stop_event.is_set():
                return True
            step = min(0.5, interval - slept)
            time.sleep(step)
            slept += step
        return bool(stop_event is not None and stop_event.is_set())

    def _discover_once(self) -> bool:
        """
            按 kind 各最多抢 1 条发现任务并执行。

            Returns:
                是否至少处理过 1 条任务（成功或失败都算「有活」）
        """
        conn = repo.connect(self.settings)
        did_work = False
        try:
            for kind in DISCOVER_REGISTRY:
                locked_by = f"py-discover-{kind}-{self.settings.worker_id}"
                task = repo.claim_crawl_task(conn, self.settings, kind, locked_by)
                if not task:
                    continue
                did_work = True
                self._run_discover_task(conn, kind, task, locked_by)
        finally:
            conn.close()
        return did_work

    def _run_discover_task(
        self, conn, kind: str, task: dict, locked_by: str
    ) -> None:
        entry = DISCOVER_REGISTRY[kind]
        budget = entry[1]
        executor = entry[2](self.settings)
        task_id = int(task["id"])
        try:
            result: DiscoverResult = executor.execute(task)
            upserted, written = repo.discover_post_success(
                conn, task, result, locked_by
            )
            for doc_id, item in written:
                embed_stub_document(
                    document_id=doc_id,
                    company_id=int(task["company_id"]),
                    title=item.title,
                    summary=item.content_summary,
                    url=item.news_url,
                    source_kind=kind,
                    worker_id=locked_by,
                )
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
            log.info(
                "发现成功 task_id=%s kind=%s upserted=%s", task_id, kind, upserted
            )
        except Exception as exc:
            log.exception("发现失败 task_id=%s kind=%s", task_id, kind)
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
            if budget.request_interval_ms > 0:
                time.sleep(budget.request_interval_ms / 1000.0)

    def _content_once(self) -> PollOutcome:
        """
            正文：批量认领入 Frontier，再按礼貌键到点弹出执行。

            Returns:
                work / empty / yielded
        """
        conn = repo.connect(self.settings)
        try:
            repo.reset_stale_content_tasks(conn, 1800)
            repo.reset_stale_crawl_tasks(
                conn, int(self.settings.crawl_stale_timeout_sec)
            )

            # 1. Frontier 空则按 kind 批量认领（发现进行中的 kind 跳过）
            if self._content_frontier.empty():
                saw_yield = False
                batch_limit = int(self.settings.content_claim_batch)
                for kind, _entry in CONTENT_REGISTRY.items():
                    if repo.has_active_crawl_tasks(conn, self.settings, kind):
                        log.info(
                            "正文让路：存在进行中的发现任务 kind=%s，本批不认领",
                            kind,
                        )
                        saw_yield = True
                        continue
                    locked_by = f"py-content-{kind}-{self.settings.worker_id}"
                    batch = repo.claim_content_tasks_batch(
                        conn,
                        self.settings,
                        kind,
                        locked_by,
                        limit=batch_limit,
                    )
                    if not batch:
                        continue
                    added = self._content_frontier.add_tasks(batch)
                    log.info(
                        "正文 Frontier 入队 kind=%s claimed=%s added=%s "
                        "frontier_size=%s keys=%s",
                        kind,
                        len(batch),
                        added,
                        len(self._content_frontier),
                        self._content_frontier.key_count(),
                    )
                if self._content_frontier.empty():
                    if saw_yield:
                        return "yielded"
                    return "empty"

            # 2. 弹出已冷却任务（必要时短等）
            pop = None
            for _ in range(4):
                pop = self._content_frontier.pop_ready()
                if pop.task is not None:
                    break
                if pop.wait_sec <= 0:
                    break
                time.sleep(min(float(pop.wait_sec), 15.0))
            if pop is None or pop.task is None:
                return "yielded"

            task = pop.task
            key = pop.key or ""
            kind = str(task.get("source_kind") or "news_html")
            entry = CONTENT_REGISTRY.get(kind)
            if entry is None:
                log.warning(
                    "未知 source_kind=%s task_id=%s，放回 PENDING",
                    kind,
                    task.get("id"),
                )
                repo.release_content_task_claim(
                    conn,
                    int(task["id"]),
                    worker_id=f"py-content-{kind}-{self.settings.worker_id}",
                )
                return "yielded"

            locked_by = f"py-content-{kind}-{self.settings.worker_id}"
            budget = entry[1]

            if repo.has_active_crawl_tasks(conn, self.settings, kind):
                log.info(
                    "正文让路：执行前发现有检索任务 kind=%s task_id=%s，放回 PENDING",
                    kind,
                    task.get("id"),
                )
                repo.release_content_task_claim(
                    conn, int(task["id"]), worker_id=locked_by
                )
                return "yielded"

            ran = self._run_content_task(
                conn, kind, task, locked_by, budget.max_attempts
            )
            gap = 0.0
            if ran and key:
                gap = self._content_frontier.mark_fetched(key)
            log.info(
                "正文 Frontier 完成 task_id=%s key=%s ran=%s gap=%.1fs "
                "remain=%s keys=%s",
                task.get("id"),
                key,
                ran,
                gap,
                len(self._content_frontier),
                self._content_frontier.key_count(),
            )
            return "work" if ran else "yielded"
        finally:
            conn.close()

    def _run_content_task(
        self,
        conn,
        kind: str,
        task: dict,
        locked_by: str,
        max_attempts: int,
    ) -> bool:
        """
            执行一条正文任务。

            Returns:
                True 表示真正开跑（含失败收尾）；False 表示让路放回未执行
        """
        entry = CONTENT_REGISTRY[kind]
        executor = entry[2](self.settings)
        task_id = int(task["id"])
        try:
            if repo.has_active_crawl_tasks(conn, self.settings, kind):
                log.debug(
                    "正文让路：执行前发现有检索任务 kind=%s task_id=%s，放回 PENDING",
                    kind,
                    task_id,
                )
                repo.release_content_task_claim(conn, task_id, worker_id=locked_by)
                return False

            result: ContentResult = executor.execute(task)
            if not result.content_text:
                err = (result.extra or {}).get("error") or "正文为空"
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
                return True

            doc = repo.get_document_by_news_url(conn, int(task["news_url_id"]))
            if not doc:
                raise RuntimeError(
                    f"缺少 stub document news_url_id={task.get('news_url_id')}"
                )
            doc_id = int(doc["id"])
            url = (task.get("url") or doc.get("url") or "").strip()

            embed_status, embed_err = embed_full_document(
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
            repo.finish_content_task_success(conn, task, result_row, locked_by)
            log.info(
                "正文成功 task_id=%s kind=%s document_id=%s embed_status=%s",
                task_id,
                kind,
                doc_id,
                embed_status,
            )
            return True
        except Exception as exc:
            log.exception("正文失败 task_id=%s kind=%s", task_id, kind)
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
            return True
