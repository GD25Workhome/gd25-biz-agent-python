"""
radar_kb 统一写库：发现后置 + 正文回写（MySQL pymysql 同步事务）。
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import pymysql
from pymysql.cursors import DictCursor

from radar_kb.config import KbSettings
from radar_kb.types import DiscoverItem, DiscoverResult

log = logging.getLogger("radar_kb.repository")

_NOT_DELETED = "deleted = b'0'"

STATUS_PENDING = 0
STATUS_RUNNING = 1
STATUS_SUCCESS = 2
STATUS_FAILED = 3

FETCH_LIST_ONLY = 0
FETCH_OK = 1
FETCH_FAILED = 2

EMBED_PENDING = 0
EMBED_OK = 1

GRADE_STUB = "stub"
GRADE_FULL = "full"


def connect(settings: KbSettings) -> pymysql.Connection:
    """创建 MySQL 连接。"""
    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


def normalize_url(url: Optional[str]) -> Optional[str]:
    """规范化 URL（去 fragment、host 小写）。"""
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return urlunparse((parsed.scheme.lower(), netloc, path, "", parsed.query, ""))
    except Exception:
        return url.strip()


def sha1_hex(text: Optional[str]) -> Optional[str]:
    """url_norm / 正文哈希用 sha1。"""
    if not text:
        return None
    return hashlib.sha1(str(text).encode("utf-8")).hexdigest()


def _truncate(value: Optional[str], limit: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[:limit]


def _tenant_clause(settings: KbSettings) -> tuple[str, list[Any]]:
    if settings.tenant_id is None:
        return "", []
    return " AND tenant_id = %s", [settings.tenant_id]


def claim_crawl_task(
    conn: pymysql.Connection, settings: KbSettings, kind: str, locked_by: str
) -> Optional[dict[str, Any]]:
    """
    按 source_kind 抢一条 PENDING 发现任务。

    Args:
        conn: 数据库连接
        settings: 配置
        kind: news_html | cninfo
        locked_by: 锁标识

    Returns:
        任务行；无任务返回 None
    """
    tenant_sql, tenant_params = _tenant_clause(settings)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id FROM radar_news_crawl_task
            WHERE {_NOT_DELETED} AND status = %s AND source_kind = %s{tenant_sql}
            ORDER BY id ASC
            LIMIT 1
            FOR UPDATE
            """,
            [STATUS_PENDING, kind, *tenant_params],
        )
        row = cur.fetchone()
        if not row:
            conn.commit()
            return None
        task_id = int(row["id"])
        now = datetime.now()
        cur.execute(
            f"""
            UPDATE radar_news_crawl_task
            SET status = %s, locked_by = %s, locked_at = %s,
                updater = %s, update_time = %s
            WHERE id = %s AND status = %s AND {_NOT_DELETED}
            """,
            (STATUS_RUNNING, locked_by, now, locked_by, now, task_id, STATUS_PENDING),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return None
        cur.execute(
            f"SELECT * FROM radar_news_crawl_task WHERE id = %s",
            (task_id,),
        )
        task = cur.fetchone()
    conn.commit()
    return task


def finish_crawl_task(
    conn: pymysql.Connection,
    task_id: int,
    *,
    worker_id: str,
    success: bool,
    stats: Optional[dict[str, Any]] = None,
    news_url_count: Optional[int] = None,
    cost_ms: Optional[int] = None,
    error_message: Optional[str] = None,
    stop_reason: Optional[str] = None,
    agent_trace_id: Optional[str] = None,
    task: Optional[dict[str, Any]] = None,
) -> None:
    """
    回写发现任务终态。

    失败时额外把最近失败信息冗余到企业源 / 全局源表（列表入口运维可见）；
    源表回写失败只打日志，不影响任务终态已提交。
    """
    now = datetime.now()
    status = STATUS_SUCCESS if success else STATUS_FAILED
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE radar_news_crawl_task
            SET status = %s, stats_json = %s, news_url_count = %s, cost_ms = %s,
                error_message = %s, stop_reason = COALESCE(%s, stop_reason),
                agent_trace_id = COALESCE(%s, agent_trace_id),
                locked_by = NULL, locked_at = NULL,
                updater = %s, update_time = %s
            WHERE id = %s AND {_NOT_DELETED}
            """,
            (
                status,
                json.dumps(stats or {}, ensure_ascii=False),
                news_url_count,
                cost_ms,
                _truncate(error_message, 1000),
                stop_reason,
                _truncate(agent_trace_id, 64),
                worker_id,
                now,
                int(task_id),
            ),
        )
    conn.commit()

    # 发现终态后强制回写源表健康态（成功清失败字段；失败写失败字段）
    try:
        record_source_discover_outcome(
            conn,
            task=task,
            task_id=int(task_id),
            success=success,
            error_message=error_message,
            worker_id=worker_id,
            event_time=now,
        )
    except Exception:
        log.exception(
            "回写信息源健康态失败 task_id=%s success=%s（任务终态已提交）",
            task_id,
            success,
        )


URL_HEALTH_UNKNOWN = "unknown"
URL_HEALTH_OK = "ok"
URL_HEALTH_FAIL = "fail"


def _resolve_source_table(
    task: Optional[dict[str, Any]],
) -> tuple[Optional[str], Optional[int]]:
    """从任务行解析源表名与 source_url_id；无法解析时返回 (None, None)。"""
    if not task:
        return None, None
    source_url_id = task.get("source_url_id")
    if source_url_id is None:
        return None, None
    try:
        source_url_id = int(source_url_id)
    except (TypeError, ValueError):
        return None, None
    if source_url_id <= 0:
        return None, None

    ref = str(task.get("source_ref_type") or "company").strip().lower()
    if ref == "global":
        return "radar_global_source_url", source_url_id
    if ref == "company":
        return "radar_company_source_url", source_url_id
    log.warning(
        "未知 source_ref_type=%s，跳过源健康态回写",
        ref,
    )
    return None, None


def record_source_discover_outcome(
    conn: pymysql.Connection,
    *,
    task: Optional[dict[str, Any]],
    task_id: int,
    success: bool,
    error_message: Optional[str],
    worker_id: str,
    event_time: Optional[datetime] = None,
) -> None:
    """
    发现终态 → 强制更新信息源健康态。

    - 失败：url_health=fail，写入 last_fail_*
    - 成功：url_health=ok，清空 last_fail_*
    - 不修改 enabled（人工开关）
    - 仅发现阶段；不写正文/详情失败
    """
    table, source_url_id = _resolve_source_table(task)
    if not table or source_url_id is None:
        return

    now = event_time or datetime.now()
    if success:
        health = URL_HEALTH_OK
        fail_task_id = None
        fail_summary = None
        fail_time = None
        fail_stage = None
    else:
        health = URL_HEALTH_FAIL
        fail_task_id = int(task_id)
        fail_summary = _truncate(error_message or "discover_failed", 500)
        fail_time = now
        fail_stage = "discover"

    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {table}
            SET url_health = %s,
                last_fail_task_id = %s,
                last_fail_summary = %s,
                last_fail_time = %s,
                last_fail_stage = %s,
                updater = %s,
                update_time = %s
            WHERE id = %s AND {_NOT_DELETED}
            """,
            (
                health,
                fail_task_id,
                fail_summary,
                fail_time,
                fail_stage,
                worker_id,
                now,
                source_url_id,
            ),
        )
        updated = int(cur.rowcount or 0)
    conn.commit()
    if updated == 0:
        log.warning(
            "信息源行未更新（可能已删）table=%s source_url_id=%s task_id=%s",
            table,
            source_url_id,
            task_id,
        )
    else:
        log.info(
            "已回写信息源健康态 table=%s source_url_id=%s task_id=%s url_health=%s",
            table,
            source_url_id,
            task_id,
            health,
        )


def record_source_discover_fail(
    conn: pymysql.Connection,
    *,
    task: Optional[dict[str, Any]],
    task_id: int,
    error_message: Optional[str],
    worker_id: str,
    fail_time: Optional[datetime] = None,
) -> None:
    """兼容旧调用：等价于发现失败回写。"""
    record_source_discover_outcome(
        conn,
        task=task,
        task_id=task_id,
        success=False,
        error_message=error_message,
        worker_id=worker_id,
        event_time=fail_time,
    )


def _find_news_url_id(
    cur: pymysql.cursors.Cursor,
    *,
    source_kind: str,
    external_id: Optional[str],
    url_hash: str,
) -> Optional[int]:
    """cninfo 优先 external_id，否则 url_hash。"""
    if external_id:
        cur.execute(
            f"""
            SELECT id FROM radar_company_news_url
            WHERE {_NOT_DELETED} AND source_kind = %s AND external_id = %s
            LIMIT 1
            """,
            (source_kind, external_id),
        )
        row = cur.fetchone()
        if row:
            return int(row["id"])
    cur.execute(
        f"""
        SELECT id FROM radar_company_news_url
        WHERE {_NOT_DELETED} AND url_hash = %s
        LIMIT 1
        """,
        (url_hash,),
    )
    row = cur.fetchone()
    return int(row["id"]) if row else None


def upsert_news_url(
    cur: pymysql.cursors.Cursor,
    *,
    task: dict[str, Any],
    item: DiscoverItem,
    worker_id: str,
) -> int:
    """
    upsert radar_company_news_url（发现后置）。

    Returns:
        news_url.id
    """
    url = (item.news_url or "").strip()
    url_norm = normalize_url(url) or ""
    url_hash = sha1_hex(url_norm) or ""
    source_kind = str(task.get("source_kind") or "news_html")
    source_ref_type = str(task.get("source_ref_type") or "company")
    source_level = str(task.get("source_level") or "P0")
    now = datetime.now()
    tenant_id = int(task.get("tenant_id") or 0)

    existing_id = _find_news_url_id(
        cur, source_kind=source_kind, external_id=item.external_id, url_hash=url_hash
    )
    fields = {
        "company_id": int(task["company_id"]),
        "source_url_id": int(task["source_url_id"]),
        "source_ref_type": source_ref_type,
        "source_kind": source_kind,
        "source_level": source_level,
        "task_id": int(task["id"]),
        "news_url": _truncate(url, 1024),
        "url_norm": _truncate(url_norm, 512),
        "url_hash": url_hash,
        "title": _truncate(item.title, 512),
        "content_summary": _truncate(item.content_summary, 1024),
        "external_id": _truncate(item.external_id, 64),
        "published_at": _truncate(item.published_at, 32),
        "published_date": item.published_date,
        "source": _truncate(item.source, 32) or "cninfo",
    }

    if existing_id:
        assignments = ", ".join(f"{k} = %s" for k in fields)
        cur.execute(
            f"""
            UPDATE radar_company_news_url
            SET {assignments}, updater = %s, update_time = %s
            WHERE id = %s
            """,
            (*fields.values(), worker_id, now, existing_id),
        )
        return existing_id

    columns = ", ".join(fields.keys())
    placeholders = ", ".join(["%s"] * len(fields))
    cur.execute(
        f"""
        INSERT INTO radar_company_news_url
            ({columns}, creator, create_time, updater, update_time, deleted, tenant_id)
        VALUES ({placeholders}, %s, %s, %s, %s, b'0', %s)
        """,
        (*fields.values(), worker_id, now, worker_id, now, tenant_id),
    )
    return int(cur.lastrowid or 0)


def upsert_stub_document(
    cur: pymysql.cursors.Cursor,
    *,
    task: dict[str, Any],
    item: DiscoverItem,
    news_url_id: int,
    worker_id: str,
) -> int:
    """
    upsert stub 文档（content_grade=stub，正文为空）。

    Returns:
        document.id
    """
    url = (item.news_url or "").strip()
    url_norm = normalize_url(url) or ""
    url_hash = sha1_hex(url_norm) or ""
    summary = _truncate(item.content_summary or item.title, 1024) or "(stub)"
    now = datetime.now()
    tenant_id = int(task.get("tenant_id") or 0)
    source_kind = str(task.get("source_kind") or "news_html")
    source_ref_type = str(task.get("source_ref_type") or "company")

    cur.execute(
        f"""
        SELECT id FROM radar_company_news_document
        WHERE news_url_id = %s AND {_NOT_DELETED}
        FOR UPDATE
        """,
        (news_url_id,),
    )
    existing = cur.fetchone()
    # 业务列（不含审计/tenant）；占位须与下方 SQL 一一对应
    biz = (
        int(task["company_id"]),
        news_url_id,
        int(task["source_url_id"]),
        _truncate(item.title, 512),
        _truncate(url, 1024),
        _truncate(url_norm, 512),
        url_hash,
        _truncate(item.published_at, 32),
        None,  # content_text
        summary,
        None,  # content_hash
        _truncate(item.source, 16) or "rule",
        str(task.get("source_level") or "P0"),
        source_kind,
        source_ref_type,
        _truncate(item.external_id, 64),
        GRADE_STUB,
        FETCH_LIST_ONLY,
        0,  # fetch_attempts
        EMBED_PENDING,
        None,  # vector_id
    )
    if existing:
        doc_id = int(existing["id"])
        cur.execute(
            f"""
            UPDATE radar_company_news_document
            SET company_id = %s, news_url_id = %s, source_url_id = %s,
                title = %s, url = %s, url_norm = %s, url_hash = %s,
                published_at = %s, content_text = %s, content_summary = %s,
                content_hash = %s, source_type = %s, source_level = %s,
                source_kind = %s, source_ref_type = %s, external_id = %s,
                content_grade = %s, fetch_status = %s, fetch_attempts = %s,
                embed_status = %s, vector_id = %s,
                updater = %s, update_time = %s, tenant_id = %s
            WHERE id = %s
            """,
            (*biz, worker_id, now, tenant_id, doc_id),
        )
        return doc_id

    cur.execute(
        f"""
        INSERT INTO radar_company_news_document
            (company_id, news_url_id, source_url_id, title, url, url_norm, url_hash,
             published_at, content_text, content_summary, content_hash, source_type,
             source_level, source_kind, source_ref_type, external_id, content_grade,
             fetch_status, fetch_attempts, embed_status, vector_id,
             creator, create_time, updater, update_time, deleted, tenant_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, b'0', %s)
        """,
        (*biz, worker_id, now, worker_id, now, tenant_id),
    )
    return int(cur.lastrowid or 0)


def insert_content_task_if_absent(
    cur: pymysql.cursors.Cursor,
    *,
    task: dict[str, Any],
    news_url_id: int,
    url: str,
    worker_id: str,
) -> bool:
    """
    插入 PENDING 正文任务（同 news_url 无活跃任务时）。

    Returns:
        True 表示新插入
    """
    cur.execute(
        f"""
        SELECT id FROM radar_news_content_task
        WHERE news_url_id = %s AND {_NOT_DELETED}
          AND status IN (%s, %s)
        LIMIT 1
        """,
        (news_url_id, STATUS_PENDING, STATUS_RUNNING),
    )
    if cur.fetchone():
        return False

    now = datetime.now()
    tenant_id = int(task.get("tenant_id") or 0)
    cur.execute(
        f"""
        INSERT INTO radar_news_content_task
            (company_id, news_url_id, source_url_id, source_kind, source_ref_type,
             source_level, url, company_name, stock_code, status, embed_status,
             triggered_by, creator, create_time, updater, update_time, deleted, tenant_id)
        VALUES (%s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, b'0', %s)
        """,
        (
            int(task["company_id"]),
            news_url_id,
            int(task["source_url_id"]),
            str(task.get("source_kind") or "news_html"),
            str(task.get("source_ref_type") or "company"),
            str(task.get("source_level") or "P0"),
            _truncate(url, 1024),
            _truncate(task.get("company_name"), 255),
            _truncate(task.get("stock_code"), 16),
            STATUS_PENDING,
            EMBED_PENDING,
            "radar_kb_discover",
            worker_id,
            now,
            worker_id,
            now,
            tenant_id,
        ),
    )
    return True


def discover_post_success(
    conn: pymysql.Connection,
    task: dict[str, Any],
    result: DiscoverResult,
    worker_id: str,
) -> tuple[int, list[tuple[int, DiscoverItem]]]:
    """
    发现成功后置：news_url + stub document + content_task（单事务）。

    Returns:
        (upsert 条数, [(document_id, DiscoverItem), ...])
    """
    upserted = 0
    written: list[tuple[int, DiscoverItem]] = []
    try:
        with conn.cursor() as cur:
            for item in result.items:
                if not (item.news_url or "").strip():
                    continue
                news_url_id = upsert_news_url(cur, task=task, item=item, worker_id=worker_id)
                doc_id = upsert_stub_document(
                    cur, task=task, item=item, news_url_id=news_url_id, worker_id=worker_id
                )
                insert_content_task_if_absent(
                    cur, task=task, news_url_id=news_url_id, url=item.news_url, worker_id=worker_id
                )
                written.append((doc_id, item))
                upserted += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return upserted, written


def claim_content_task(
    conn: pymysql.Connection, settings: KbSettings, kind: str, locked_by: str
) -> Optional[dict[str, Any]]:
    """按 source_kind 抢一条 PENDING 正文任务。"""
    tenant_sql, tenant_params = _tenant_clause(settings)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id FROM radar_news_content_task
            WHERE {_NOT_DELETED} AND status = %s AND source_kind = %s{tenant_sql}
            ORDER BY id ASC
            LIMIT 1
            FOR UPDATE
            """,
            [STATUS_PENDING, kind, *tenant_params],
        )
        row = cur.fetchone()
        if not row:
            conn.commit()
            return None
        task_id = int(row["id"])
        now = datetime.now()
        cur.execute(
            f"""
            UPDATE radar_news_content_task
            SET status = %s, locked_by = %s, locked_at = %s,
                updater = %s, update_time = %s
            WHERE id = %s AND status = %s AND {_NOT_DELETED}
            """,
            (STATUS_RUNNING, locked_by, now, locked_by, now, task_id, STATUS_PENDING),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return None
        cur.execute(
            f"SELECT * FROM radar_news_content_task WHERE id = %s",
            (task_id,),
        )
        task = cur.fetchone()
    conn.commit()
    return task


def has_active_crawl_tasks(
    conn: pymysql.Connection,
    settings: KbSettings,
    kind: str,
) -> bool:
    """
    是否存在同 kind 的进行中发现任务（PENDING / RUNNING）。

    用于正文让路：有检索则先跑检索，PDF/正文后至。
    """
    tenant_sql, tenant_params = _tenant_clause(settings)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT 1 FROM radar_news_crawl_task
            WHERE {_NOT_DELETED}
              AND source_kind = %s
              AND status IN (%s, %s)
              {tenant_sql}
            LIMIT 1
            """,
            [kind, STATUS_PENDING, STATUS_RUNNING, *tenant_params],
        )
        return cur.fetchone() is not None


def release_content_task_claim(
    conn: pymysql.Connection,
    task_id: int,
    *,
    worker_id: str,
) -> None:
    """
    将已抢到的正文任务放回 PENDING（让路检索，不算失败）。

    仅当仍由本 worker 持锁且状态为 RUNNING 时生效。
    """
    now = datetime.now()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE radar_news_content_task
            SET status = %s, locked_by = NULL, locked_at = NULL,
                updater = %s, update_time = %s
            WHERE id = %s AND status = %s AND locked_by = %s AND {_NOT_DELETED}
            """,
            (
                STATUS_PENDING,
                worker_id,
                now,
                task_id,
                STATUS_RUNNING,
                worker_id,
            ),
        )
    conn.commit()


def finish_content_task_success(
    conn: pymysql.Connection,
    content_task: dict[str, Any],
    result_row: dict[str, Any],
    worker_id: str,
) -> None:
    """正文成功：更新 document 为 full + 回写 content_task。"""
    now = datetime.now()
    doc_id = int(result_row["document_id"])
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE radar_company_news_document
            SET title = %s, published_at = %s, content_text = %s, content_summary = %s,
                content_hash = %s, source_type = %s, content_grade = %s,
                fetch_status = %s, embed_status = %s,
                updater = %s, update_time = %s
            WHERE id = %s AND {_NOT_DELETED}
            """,
            (
                result_row.get("title"),
                result_row.get("published_at"),
                result_row.get("content_text"),
                result_row.get("content_summary"),
                result_row.get("content_hash"),
                result_row.get("actual_channel"),
                GRADE_FULL,
                FETCH_OK,
                result_row.get("embed_status", EMBED_PENDING),
                worker_id,
                now,
                doc_id,
            ),
        )
        cur.execute(
            f"""
            UPDATE radar_news_content_task
            SET status = %s, document_id = %s, actual_channel = %s,
                title = %s, published_at = %s, content_hash = %s,
                embed_status = %s, cost_ms = %s, agent_trace_id = %s,
                error_message = NULL, locked_by = NULL, locked_at = NULL,
                updater = %s, update_time = %s
            WHERE id = %s AND {_NOT_DELETED}
            """,
            (
                STATUS_SUCCESS,
                doc_id,
                result_row.get("actual_channel"),
                result_row.get("title"),
                result_row.get("published_at"),
                result_row.get("content_hash"),
                result_row.get("embed_status", EMBED_PENDING),
                result_row.get("cost_ms"),
                result_row.get("agent_trace_id"),
                worker_id,
                now,
                int(content_task["id"]),
            ),
        )
    conn.commit()


def finish_content_task_failure(
    conn: pymysql.Connection,
    content_task: dict[str, Any],
    *,
    worker_id: str,
    error_message: str,
    actual_channel: Optional[str],
    cost_ms: Optional[int],
    agent_trace_id: Optional[str],
    max_attempts: int,
) -> None:
    """正文失败：fetch_attempts+1，未超限则回到 PENDING。"""
    now = datetime.now()
    news_url_id = int(content_task.get("news_url_id") or 0)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, fetch_attempts FROM radar_company_news_document
            WHERE news_url_id = %s AND {_NOT_DELETED}
            FOR UPDATE
            """,
            (news_url_id,),
        )
        doc = cur.fetchone()
        attempts = int(doc.get("fetch_attempts") or 0) + 1 if doc else 1
        if doc:
            cur.execute(
                f"""
                UPDATE radar_company_news_document
                SET fetch_attempts = %s, fetch_status = %s, updater = %s, update_time = %s
                WHERE id = %s
                """,
                (attempts, FETCH_FAILED, worker_id, now, int(doc["id"])),
            )

        if attempts < max_attempts:
            task_status = STATUS_PENDING
        else:
            task_status = STATUS_FAILED

        cur.execute(
            f"""
            UPDATE radar_news_content_task
            SET status = %s, actual_channel = COALESCE(%s, actual_channel),
                error_message = %s, cost_ms = %s, agent_trace_id = %s,
                locked_by = NULL, locked_at = NULL,
                updater = %s, update_time = %s
            WHERE id = %s AND {_NOT_DELETED}
            """,
            (
                task_status,
                _truncate(actual_channel, 16),
                _truncate(error_message, 1000),
                cost_ms,
                _truncate(agent_trace_id, 64),
                worker_id,
                now,
                int(content_task["id"]),
            ),
        )
    conn.commit()


def reset_stale_content_tasks(conn: pymysql.Connection, timeout_sec: int) -> int:
    """回收超时 RUNNING 正文任务。"""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE radar_news_content_task
            SET status = %s, locked_by = NULL, locked_at = NULL, update_time = NOW()
            WHERE status = %s AND {_NOT_DELETED}
              AND (locked_at IS NULL OR locked_at < DATE_SUB(NOW(), INTERVAL %s SECOND))
            """,
            (STATUS_PENDING, STATUS_RUNNING, int(timeout_sec)),
        )
        affected = int(cur.rowcount or 0)
    conn.commit()
    return affected


def get_document_by_news_url(conn: pymysql.Connection, news_url_id: int) -> Optional[dict[str, Any]]:
    """按 news_url_id 取 document 行。"""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT * FROM radar_company_news_document
            WHERE news_url_id = %s AND {_NOT_DELETED}
            LIMIT 1
            """,
            (news_url_id,),
        )
        return cur.fetchone()
