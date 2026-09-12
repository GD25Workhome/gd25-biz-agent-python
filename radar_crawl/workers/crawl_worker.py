"""
阶段 A：画像证据列表采集 Worker。

只检索并落库元数据（fetch_status=仅列表），不下 PDF。
正文由 pdf_fill_worker（阶段 B）回填。

运行：
    python -m radar_crawl crawl
    # 或
    python -m radar_crawl.workers.crawl_worker
"""

from __future__ import annotations

import json
import logging
import time

from radar_crawl.adapters import cninfo
from radar_crawl.config import load_settings
from radar_crawl.db import repository as repo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
log = logging.getLogger("radar.worker")


def run_cninfo_list_only(conn, settings, task: dict) -> dict:
    """
    阶段 A：巨潮列表元数据整批入库，禁止下载 PDF。

    Returns:
        searched / matched / inserted / duplicate
    """
    stats = {
        "searched": 0,
        "matched": 0,
        "inserted": 0,
        "duplicate": 0,
    }
    company_id = task["company_id"]
    company_name = (task.get("company_name") or "").strip()
    stock_code = (task.get("stock_code") or "").strip()
    if not company_name:
        raise RuntimeError("企业名称为空，无法检索巨潮")
    if not stock_code:
        raise RuntimeError("证券代码为空，无法过滤巨潮结果")

    time_from = task.get("time_from")
    time_to = task.get("time_to")
    sdate = time_from.strftime("%Y-%m-%d") if hasattr(time_from, "strftime") else str(time_from)
    edate = time_to.strftime("%Y-%m-%d") if hasattr(time_to, "strftime") else str(time_to)

    raw_list = cninfo.search_announcements(
        company_name,
        sdate=sdate,
        edate=edate,
        page_size=settings.cninfo_page_size,
        max_pages=settings.cninfo_max_pages,
        interval_sec=settings.request_interval_sec,
    )
    stats["searched"] = len(raw_list)
    matched = cninfo.filter_by_stock_code(raw_list, stock_code)
    stats["matched"] = len(matched)
    log.info(
        "检索结束 task_id=%s company=%s(%s) searched=%s matched=%s",
        task["id"],
        company_name,
        stock_code,
        stats["searched"],
        stats["matched"],
    )

    for item in matched:
        repo.heartbeat(conn, int(task["id"]), settings)
        external_id = str(item.get("announcementId") or item.get("id") or "") or None
        adjunct = item.get("adjunctUrl")
        pdf_url = cninfo.build_pdf_url(adjunct)
        url = pdf_url or item.get("url") or ""
        url_norm = repo.normalize_url(url) if url else None
        title = (item.get("announcementTitle") or item.get("shortTitle") or "")[:512]
        summary = cninfo.make_summary(
            item.get("announcementContent"),
            title,
            settings.summary_max_chars,
        )
        published_at = cninfo.parse_announcement_time(item.get("announcementTime"))

        dup_id = repo.find_duplicate(
            conn,
            settings,
            source_type="cninfo",
            external_id=external_id,
            url_norm=url_norm,
            c_hash=None,
        )
        if dup_id:
            repo.touch_duplicate(conn, dup_id, int(task["id"]), settings)
            stats["duplicate"] += 1
            continue

        extra = {
            "secCode": item.get("secCode"),
            "secName": item.get("secName"),
            "announcementTypeName": item.get("announcementTypeName"),
            "adjunctUrl": adjunct,
        }
        repo.insert_document(
            conn,
            settings,
            {
                "company_id": company_id,
                "crawl_task_id": int(task["id"]),
                "source_type": "cninfo",
                "source_level": "P0",
                "external_id": external_id,
                "title": title,
                "url": url or None,
                "url_norm": url_norm,
                "published_at": published_at,
                "content_text": None,
                "content_summary": summary,
                "content_hash": None,
                "extra_json": json.dumps(extra, ensure_ascii=False),
                "verify_flag": 0,
                "fetch_status": repo.FETCH_LIST_ONLY,
                "tenant_id": task.get("tenant_id"),
            },
        )
        stats["inserted"] += 1

    log.info(
        "落库汇总 task_id=%s inserted=%s duplicate=%s",
        task["id"],
        stats["inserted"],
        stats["duplicate"],
    )
    return stats


def process_task(conn, settings, task: dict) -> None:
    """处理单条列表采集任务。"""
    source_types = (task.get("source_types") or "cninfo").split(",")
    source_types = [s.strip().lower() for s in source_types if s.strip()]
    all_stats: dict = {"phase": "LIST", "sources": {}}
    try:
        if "cninfo" in source_types:
            all_stats["sources"]["cninfo"] = run_cninfo_list_only(conn, settings, task)
        repo.finish_task(conn, int(task["id"]), settings, success=True, stats=all_stats)
        log.info("任务成功 task_id=%s stats=%s", task["id"], json.dumps(all_stats, ensure_ascii=False))
    except Exception as exc:
        log.error(
            "任务失败 task_id=%s company_id=%s err=%s",
            task.get("id"),
            task.get("company_id"),
            exc,
            exc_info=True,
        )
        repo.finish_task(
            conn,
            int(task["id"]),
            settings,
            success=False,
            stats=all_stats,
            error_message=str(exc),
        )


def main() -> None:
    """阶段 A 主循环。"""
    settings = load_settings()
    log.info(
        "Worker 启动(阶段A-列表) worker_id=%s db=%s@%s/%s poll=%ss tenant=%s fetch_pdf_switch=%s",
        settings.worker_id,
        settings.db_user,
        settings.db_host,
        settings.db_name,
        settings.poll_interval_sec,
        settings.tenant_id if settings.tenant_id is not None else "ANY(未配置)",
        settings.cninfo_fetch_pdf,
    )
    while True:
        conn = None
        try:
            conn = repo.connect(settings)
            task = repo.claim_one_task(conn, settings)
            if task is None:
                conn.close()
                time.sleep(settings.poll_interval_sec)
                continue
            log.info(
                "领取任务 task_id=%s company_id=%s company=%s stock=%s purpose=%s window=%s~%s",
                task["id"],
                task.get("company_id"),
                task.get("company_name"),
                task.get("stock_code"),
                task.get("purpose"),
                task.get("time_from"),
                task.get("time_to"),
            )
            process_task(conn, settings, task)
            conn.close()
            time.sleep(settings.request_interval_sec)
        except KeyboardInterrupt:
            log.info("收到中断，退出")
            if conn:
                conn.close()
            break
        except Exception:
            log.exception("主循环异常，将休眠后重试")
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            time.sleep(settings.poll_interval_sec)


if __name__ == "__main__":
    main()
