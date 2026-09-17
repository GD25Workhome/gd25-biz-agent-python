"""
阶段 B：PDF 正文回填 Worker（独立进程 + 多协程）。

扫描 fetch_status=仅列表 且有 URL 的证据行，限速下载并抽字回写。

运行：
    python -m radar_crawl pdf
    # 或
    python -m radar_crawl.workers.pdf_fill_worker
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from radar_crawl.adapters import cninfo
from radar_crawl.config import Settings, load_settings
from radar_crawl.db import repository as repo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
log = logging.getLogger("radar.pdf")


class GlobalRateLimiter:
    """
    全进程 HTTP 最小间隔（协程共享一把锁）。

    说明：巨潮 PDF 下载已改由 ``cninfo`` 适配器线程锁限速；本类保留给其它
    调用方或排障，当前 pdf_fill 主路径不再使用。
    """

    def __init__(self, interval_sec: float) -> None:
        self._interval = max(0.0, interval_sec)
        self._lock = asyncio.Lock()
        self._last_ts = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait_sec = self._interval - (now - self._last_ts)
            if wait_sec > 0:
                log.debug("限速等待 ms=%s", int(wait_sec * 1000))
                await asyncio.sleep(wait_sec)
            self._last_ts = time.monotonic()


def _truncate_url(url: str, max_len: int = 120) -> str:
    if not url:
        return ""
    return url if len(url) <= max_len else url[:max_len] + "..."


async def fill_one(
    settings: Settings,
    doc: dict[str, Any],
    sem: asyncio.Semaphore,
) -> str:
    """
    处理单条证据正文。

    Returns:
        ok / fail / skip
    """
    doc_id = int(doc["id"])
    url = (doc.get("url") or "").strip()
    async with sem:
        log.debug(
            "单条开始 doc_id=%s company_id=%s url=%s",
            doc_id,
            doc.get("company_id"),
            _truncate_url(url),
        )
        conn = None
        try:
            # 再确认是否已有正文（防误领）
            conn = await asyncio.to_thread(repo.connect, settings)
            brief = await asyncio.to_thread(repo.get_document_brief, conn, doc_id)
            if brief and int(brief.get("has_text") or 0) == 1:
                log.debug("跳过 doc_id=%s reason=already_has_content", doc_id)
                await asyncio.to_thread(repo.clear_content_lock, conn, settings, doc_id)
                return "skip"

            if not url:
                await asyncio.to_thread(
                    repo.mark_document_pdf_failed,
                    conn,
                    settings,
                    doc_id,
                    error_message="empty_url",
                )
                log.warning("单条失败 doc_id=%s url= empty_url", doc_id)
                return "fail"

            # 限速在 cninfo 适配器内（线程锁 + 5s/抖动）；此处不再叠一层 wait
            text, err = await asyncio.to_thread(
                cninfo.download_and_extract_text,
                url,
                max_chars=settings.content_text_max_chars,
                max_pages=settings.pdf_max_pages,
            )
            if not text:
                await asyncio.to_thread(
                    repo.mark_document_pdf_failed,
                    conn,
                    settings,
                    doc_id,
                    error_message=err or "unknown",
                )
                log.warning(
                    "单条失败 doc_id=%s url=%s err=%s",
                    doc_id,
                    _truncate_url(url),
                    err,
                )
                return "fail"

            c_hash = repo.content_hash(text)
            await asyncio.to_thread(
                repo.update_document_content,
                conn,
                settings,
                doc_id,
                content_text=text,
                content_hash_value=c_hash,
                fetch_status=repo.FETCH_CONTENT_OK,
                crawl_task_id=doc.get("crawl_task_id"),
            )
            log.info(
                "单条成功 doc_id=%s external_id=%s chars=%s fetch_status=1",
                doc_id,
                doc.get("external_id"),
                len(text),
            )
            return "ok"
        except Exception as exc:
            log.warning(
                "单条失败 doc_id=%s url=%s err=%s",
                doc_id,
                _truncate_url(url),
                exc,
            )
            try:
                if conn is None:
                    conn = await asyncio.to_thread(repo.connect, settings)
                await asyncio.to_thread(
                    repo.mark_document_pdf_failed,
                    conn,
                    settings,
                    doc_id,
                    error_message=str(exc)[:500],
                )
            except Exception:
                log.exception("写失败状态异常 doc_id=%s", doc_id)
            return "fail"
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass


async def run_batch(settings: Settings, docs: list[dict[str, Any]]) -> dict[str, int]:
    """并发处理一批文档。"""
    sem = asyncio.Semaphore(max(1, settings.pdf_concurrency))
    results = await asyncio.gather(
        *[fill_one(settings, doc, sem) for doc in docs],
        return_exceptions=False,
    )
    summary = {"ok": 0, "fail": 0, "skip": 0}
    for r in results:
        if r in summary:
            summary[r] += 1
        else:
            summary["fail"] += 1
    return summary


def main() -> None:
    """阶段 B 主循环。"""
    from radar_kb.config import is_legacy_crawl_disabled

    if is_legacy_crawl_disabled():
        log.warning(
            "RADAR_KB_UNIFIED=1：legacy pdf_fill_worker 已停用，请使用 python -m radar_kb content"
        )
        return
    settings = load_settings()
    log.info(
        "Worker 启动(阶段B-PDF) worker_id=%s concurrency=%s batch=%s interval=%ss "
        "poll=%ss fetch_pdf=%s tenant=%s",
        settings.worker_id,
        settings.pdf_concurrency,
        settings.pdf_batch_size,
        settings.request_interval_sec,
        settings.pdf_poll_interval_sec,
        settings.cninfo_fetch_pdf,
        settings.tenant_id if settings.tenant_id is not None else "ANY(未配置)",
    )
    if not settings.cninfo_fetch_pdf:
        log.warning("RADAR_CNINFO_FETCH_PDF=关，阶段 B 空转休眠（不退出进程，便于改配置热观察）")

    while True:
        try:
            if not settings.cninfo_fetch_pdf:
                time.sleep(settings.pdf_poll_interval_sec)
                continue

            conn = repo.connect(settings)
            try:
                docs = repo.claim_docs_for_pdf(
                    conn, settings, batch_size=settings.pdf_batch_size
                )
            finally:
                conn.close()

            if not docs:
                log.debug("空闲：本轮无待抽正文文档")
                time.sleep(settings.pdf_poll_interval_sec)
                continue

            log.info("本轮领取 claimed=%s", len(docs))
            started = time.monotonic()
            summary = asyncio.run(run_batch(settings, docs))
            elapsed = time.monotonic() - started
            log.info(
                "本轮汇总 ok=%s fail=%s skip=%s elapsed_sec=%.1f",
                summary["ok"],
                summary["fail"],
                summary["skip"],
                elapsed,
            )
        except KeyboardInterrupt:
            log.info("收到中断，退出")
            break
        except Exception:
            log.exception("主循环异常，将休眠后重试")
            time.sleep(settings.pdf_poll_interval_sec)


if __name__ == "__main__":
    main()
