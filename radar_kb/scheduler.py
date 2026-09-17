"""
TaskScheduler：scan → claim → execute → post_success / post_failure。
"""
from __future__ import annotations

import logging
import time
from typing import Literal

from radar_kb import repository as repo
from radar_kb.config import KbSettings
from radar_kb.embed import embed_full_document, embed_stub_document
from radar_kb.registry import CONTENT_REGISTRY, DISCOVER_REGISTRY
from radar_kb.types import ContentResult, DiscoverResult

log = logging.getLogger("radar_kb.scheduler")

SchedulerMode = Literal["discover", "content"]


class TaskScheduler:
    """发现或正文调度器实例。"""

    def __init__(self, settings: KbSettings, mode: SchedulerMode) -> None:
        self.settings = settings
        self.mode = mode

    def run_forever(self, stop_event=None) -> None:
        """
        主循环：按 kind 扫描 pending 任务。

        Args:
            stop_event: 可选 threading.Event；置位后在本轮结束后退出（L2 应用内停机用）
        """
        log.info("调度器启动 mode=%s worker_id=%s", self.mode, self.settings.worker_id)
        while True:
            if stop_event is not None and stop_event.is_set():
                log.info("收到停止信号，退出 mode=%s", self.mode)
                break
            try:
                if self.mode == "discover":
                    self._discover_once()
                else:
                    self._content_once()
            except KeyboardInterrupt:
                log.info("收到中断，退出 mode=%s", self.mode)
                break
            except Exception:
                log.exception("调度循环异常 mode=%s", self.mode)
            # 分段 sleep，便于尽快响应 stop
            slept = 0.0
            interval = float(self.settings.poll_interval_sec)
            while slept < interval:
                if stop_event is not None and stop_event.is_set():
                    break
                step = min(0.5, interval - slept)
                time.sleep(step)
                slept += step
            if stop_event is not None and stop_event.is_set():
                log.info("收到停止信号，退出 mode=%s", self.mode)
                break

    def _discover_once(self) -> None:
        conn = repo.connect(self.settings)
        try:
            for kind in DISCOVER_REGISTRY:
                locked_by = f"py-discover-{kind}-{self.settings.worker_id}"
                task = repo.claim_crawl_task(conn, self.settings, kind, locked_by)
                if not task:
                    continue
                self._run_discover_task(conn, kind, task, locked_by)
        finally:
            conn.close()

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

    def _content_once(self) -> None:
        conn = repo.connect(self.settings)
        try:
            repo.reset_stale_content_tasks(conn, 1800)
            for kind, entry in CONTENT_REGISTRY.items():
                # 同 kind 有发现任务时让路：先检索，再 PDF/正文
                if repo.has_active_crawl_tasks(conn, self.settings, kind):
                    log.info(
                        "正文让路：存在进行中的发现任务 kind=%s，本轮跳过",
                        kind,
                    )
                    continue
                budget = entry[1]
                locked_by = f"py-content-{kind}-{self.settings.worker_id}"
                task = repo.claim_content_task(conn, self.settings, kind, locked_by)
                if not task:
                    continue
                # 抢锁后再确认一次，缩小与 discover 的竞态窗口
                if repo.has_active_crawl_tasks(conn, self.settings, kind):
                    log.info(
                        "正文让路：抢锁后发现有检索任务 kind=%s task_id=%s，放回 PENDING",
                        kind,
                        task.get("id"),
                    )
                    repo.release_content_task_claim(
                        conn, int(task["id"]), worker_id=locked_by
                    )
                    continue
                self._run_content_task(conn, kind, task, locked_by, budget.max_attempts)
        finally:
            conn.close()

    def _run_content_task(
        self,
        conn,
        kind: str,
        task: dict,
        locked_by: str,
        max_attempts: int,
    ) -> None:
        entry = CONTENT_REGISTRY[kind]
        executor = entry[2](self.settings)
        task_id = int(task["id"])
        try:
            # 下载前最后一次让路（尤其 cninfo 与检索共用出网）
            if repo.has_active_crawl_tasks(conn, self.settings, kind):
                log.info(
                    "正文让路：执行前发现有检索任务 kind=%s task_id=%s，放回 PENDING",
                    kind,
                    task_id,
                )
                repo.release_content_task_claim(conn, task_id, worker_id=locked_by)
                return

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
                return

            doc = repo.get_document_by_news_url(conn, int(task["news_url_id"]))
            if not doc:
                raise RuntimeError(f"缺少 stub document news_url_id={task.get('news_url_id')}")
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
