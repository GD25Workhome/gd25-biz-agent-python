"""
数据库访问：抢任务、写证据、心跳与状态回写。
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

from radar_crawl.config import Settings

log = logging.getLogger("radar.db")

# 任务状态：与 Java RadarCrawlTaskStatusEnum 对齐
STATUS_PENDING = 0
STATUS_RUNNING = 1
STATUS_SUCCESS = 2
STATUS_FAILED = 3

# 文档抓取状态
FETCH_LIST_ONLY = 0
FETCH_CONTENT_OK = 1
FETCH_FAILED = 2


def connect(settings: Settings) -> pymysql.Connection:
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
    """规范化 URL：去 fragment、统一小写 host。"""
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        # 去掉末尾多余斜杠（根路径除外）
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return urlunparse((parsed.scheme.lower(), netloc, path, "", parsed.query, ""))
    except Exception:
        return url.strip()


def content_hash(text: Optional[str]) -> Optional[str]:
    """正文哈希：空白归一后再算 sha256。"""
    if not text:
        return None
    normalized = " ".join(text.split())
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _tenant_sql_and_params(settings: Settings) -> tuple[str, list[Any]]:
    """
    租户过滤片段。

    未配置 RADAR_TENANT_ID 时不加 tenant 条件（开发期单库联调）。
    """
    if settings.tenant_id is None:
        return "", []
    return " AND tenant_id = %s", [settings.tenant_id]


def claim_one_task(conn: pymysql.Connection, settings: Settings) -> Optional[dict[str, Any]]:
    """
    抢一条 PENDING 任务。

    使用「先选 id 再条件更新」避免多 worker 重复领取。
    """
    tenant_sql, tenant_params = _tenant_sql_and_params(settings)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id FROM radar_crawl_task
            WHERE deleted = b'0' AND status = %s{tenant_sql}
            ORDER BY priority DESC, id ASC
            LIMIT 1
            FOR UPDATE
            """,
            [STATUS_PENDING, *tenant_params],
        )
        row = cur.fetchone()
        if not row:
            conn.commit()
            return None
        task_id = row["id"]
        now = datetime.now()
        cur.execute(
            """
            UPDATE radar_crawl_task
            SET status = %s, locked_by = %s, locked_at = %s, heartbeat_at = %s,
                updater = %s, update_time = %s
            WHERE id = %s AND status = %s AND deleted = b'0'
            """,
            (
                STATUS_RUNNING,
                settings.worker_id,
                now,
                now,
                settings.worker_id,
                now,
                task_id,
                STATUS_PENDING,
            ),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return None
        cur.execute(
            """
            SELECT t.*, c.name AS company_name, c.stock_code
            FROM radar_crawl_task t
            LEFT JOIN radar_company c ON c.id = t.company_id AND c.deleted = b'0'
            WHERE t.id = %s
            """,
            (task_id,),
        )
        task = cur.fetchone()
        conn.commit()
        return task


def heartbeat(conn: pymysql.Connection, task_id: int, settings: Settings) -> None:
    """刷新任务心跳。"""
    now = datetime.now()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE radar_crawl_task
            SET heartbeat_at = %s, updater = %s, update_time = %s
            WHERE id = %s AND status = %s
            """,
            (now, settings.worker_id, now, task_id, STATUS_RUNNING),
        )
    conn.commit()


def finish_task(
    conn: pymysql.Connection,
    task_id: int,
    settings: Settings,
    *,
    success: bool,
    stats: dict[str, Any],
    error_message: Optional[str] = None,
) -> None:
    """回写任务终态。"""
    now = datetime.now()
    status = STATUS_SUCCESS if success else STATUS_FAILED
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE radar_crawl_task
            SET status = %s, result_stats_json = %s, error_message = %s,
                heartbeat_at = %s, updater = %s, update_time = %s
            WHERE id = %s
            """,
            (
                status,
                json.dumps(stats, ensure_ascii=False),
                (error_message or "")[:1000] or None,
                now,
                settings.worker_id,
                now,
                task_id,
            ),
        )
    conn.commit()


def find_duplicate(
    conn: pymysql.Connection,
    settings: Settings,
    *,
    source_type: str,
    external_id: Optional[str],
    url_norm: Optional[str],
    c_hash: Optional[str],
) -> Optional[int]:
    """
    去重查找：优先 external_id，其次 url_norm，再次 content_hash。

    返回已有文档 id；无则 None。
    """
    tenant_sql, tenant_params = _tenant_sql_and_params(settings)
    with conn.cursor() as cur:
        if external_id:
            cur.execute(
                f"""
                SELECT id FROM radar_raw_document
                WHERE deleted = b'0'{tenant_sql}
                  AND source_type = %s AND external_id = %s
                LIMIT 1
                """,
                [*tenant_params, source_type, external_id],
            )
            row = cur.fetchone()
            if row:
                return int(row["id"])
        if url_norm:
            cur.execute(
                f"""
                SELECT id FROM radar_raw_document
                WHERE deleted = b'0'{tenant_sql} AND url_norm = %s
                LIMIT 1
                """,
                [*tenant_params, url_norm],
            )
            row = cur.fetchone()
            if row:
                return int(row["id"])
        if c_hash:
            cur.execute(
                f"""
                SELECT id FROM radar_raw_document
                WHERE deleted = b'0'{tenant_sql} AND content_hash = %s
                LIMIT 1
                """,
                [*tenant_params, c_hash],
            )
            row = cur.fetchone()
            if row:
                return int(row["id"])
    return None


def get_document_brief(conn: pymysql.Connection, doc_id: int) -> Optional[dict[str, Any]]:
    """查询证据简要信息（是否已有正文）。"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, company_id, url, fetch_status,
                   CASE
                     WHEN content_text IS NOT NULL AND content_text <> '' THEN 1
                     ELSE 0
                   END AS has_text
            FROM radar_raw_document
            WHERE id = %s AND deleted = b'0'
            """,
            (doc_id,),
        )
        return cur.fetchone()


def touch_duplicate(conn: pymysql.Connection, doc_id: int, crawl_task_id: int, settings: Settings) -> None:
    """重复命中时仅刷新关联任务与更新时间，不改正文。"""
    now = datetime.now()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE radar_raw_document
            SET crawl_task_id = %s, updater = %s, update_time = %s
            WHERE id = %s
            """,
            (crawl_task_id, settings.worker_id, now, doc_id),
        )
    conn.commit()


def resolve_write_tenant_id(settings: Settings, doc: dict[str, Any]) -> int:
    """
    写入证据时的 tenant_id。

    优先用文档/任务自带值；否则用配置；都没有则 0（与表默认一致）。
    """
    if doc.get("tenant_id") is not None:
        return int(doc["tenant_id"])
    if settings.tenant_id is not None:
        return int(settings.tenant_id)
    return 0


def insert_document(
    conn: pymysql.Connection,
    settings: Settings,
    doc: dict[str, Any],
) -> int:
    """插入新证据文档，返回 id。"""
    now = datetime.now()
    tenant_id = resolve_write_tenant_id(settings, doc)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO radar_raw_document (
                company_id, crawl_task_id, source_type, source_level, external_id,
                title, url, url_norm, published_at, content_text, content_summary,
                content_hash, extra_json, verify_flag, fetch_status,
                creator, create_time, updater, update_time, deleted, tenant_id
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, b'0', %s
            )
            """,
            (
                doc.get("company_id"),
                doc.get("crawl_task_id"),
                doc.get("source_type"),
                doc.get("source_level", "P0"),
                doc.get("external_id"),
                doc.get("title"),
                doc.get("url"),
                doc.get("url_norm"),
                doc.get("published_at"),
                doc.get("content_text"),
                doc.get("content_summary"),
                doc.get("content_hash"),
                doc.get("extra_json"),
                doc.get("verify_flag", 0),
                doc.get("fetch_status", FETCH_LIST_ONLY),
                settings.worker_id,
                now,
                settings.worker_id,
                now,
                tenant_id,
            ),
        )
        doc_id = int(cur.lastrowid)
    conn.commit()
    return doc_id


_LOCK_COLUMNS_CACHE: Optional[bool] = None


def _has_content_lock_columns(conn: pymysql.Connection) -> bool:
    """检测是否已执行 content_locked_* 迁移（进程内缓存）。"""
    global _LOCK_COLUMNS_CACHE
    if _LOCK_COLUMNS_CACHE is not None:
        return _LOCK_COLUMNS_CACHE
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'radar_raw_document'
              AND COLUMN_NAME = 'content_locked_by'
            """
        )
        row = cur.fetchone()
        _LOCK_COLUMNS_CACHE = bool(row and int(row["cnt"]) > 0)
        return _LOCK_COLUMNS_CACHE


def claim_docs_for_pdf(
    conn: pymysql.Connection,
    settings: Settings,
    *,
    batch_size: int,
) -> list[dict[str, Any]]:
    """
    领取一批待抽 PDF 的证据行（阶段 B）。

    条件：cninfo、fetch_status=0、有 url、无正文；优先用租约锁列。
    """
    tenant_sql, tenant_params = _tenant_sql_and_params(settings)
    use_lock = _has_content_lock_columns(conn)
    now = datetime.now()
    with conn.cursor() as cur:
        if use_lock:
            # 超时未完成的锁可被回收再领
            cur.execute(
                f"""
                SELECT id, company_id, crawl_task_id, external_id, title, url, url_norm,
                       tenant_id, extra_json
                FROM radar_raw_document
                WHERE deleted = b'0'
                  AND source_type = 'cninfo'
                  AND fetch_status = %s
                  AND url IS NOT NULL AND url <> ''
                  AND (content_text IS NULL OR content_text = '')
                  AND (
                    content_locked_by IS NULL
                    OR content_locked_at IS NULL
                    OR content_locked_at < DATE_SUB(NOW(), INTERVAL %s SECOND)
                  )
                  {tenant_sql}
                ORDER BY id ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                [
                    FETCH_LIST_ONLY,
                    int(settings.pdf_lock_timeout_sec),
                    *tenant_params,
                    batch_size,
                ],
            )
        else:
            cur.execute(
                f"""
                SELECT id, company_id, crawl_task_id, external_id, title, url, url_norm,
                       tenant_id, extra_json
                FROM radar_raw_document
                WHERE deleted = b'0'
                  AND source_type = 'cninfo'
                  AND fetch_status = %s
                  AND url IS NOT NULL AND url <> ''
                  AND (content_text IS NULL OR content_text = '')
                  {tenant_sql}
                ORDER BY id ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                [FETCH_LIST_ONLY, *tenant_params, batch_size],
            )
        rows = list(cur.fetchall() or [])
        if not rows:
            conn.commit()
            return []
        ids = [int(r["id"]) for r in rows]
        if use_lock:
            format_ids = ",".join(["%s"] * len(ids))
            cur.execute(
                f"""
                UPDATE radar_raw_document
                SET content_locked_by = %s, content_locked_at = %s,
                    updater = %s, update_time = %s
                WHERE id IN ({format_ids})
                """,
                [settings.worker_id, now, settings.worker_id, now, *ids],
            )
        conn.commit()
        return rows


def clear_content_lock(conn: pymysql.Connection, settings: Settings, doc_id: int) -> None:
    """释放 PDF 租约锁（若无锁列则 noop）。"""
    if not _has_content_lock_columns(conn):
        return
    now = datetime.now()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE radar_raw_document
            SET content_locked_by = NULL, content_locked_at = NULL,
                updater = %s, update_time = %s
            WHERE id = %s
            """,
            (settings.worker_id, now, doc_id),
        )
    conn.commit()


def mark_document_pdf_failed(
    conn: pymysql.Connection,
    settings: Settings,
    doc_id: int,
    *,
    error_message: str,
) -> None:
    """正文抽取失败：fetch_status=2，写错误到 extra_json.pdf_error，释放锁。"""
    now = datetime.now()
    use_lock = _has_content_lock_columns(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT extra_json FROM radar_raw_document WHERE id = %s AND deleted = b'0'",
            (doc_id,),
        )
        row = cur.fetchone()
        extra: dict[str, Any] = {}
        if row and row.get("extra_json"):
            try:
                extra = json.loads(row["extra_json"]) if isinstance(row["extra_json"], str) else {}
            except Exception:
                extra = {}
        if not isinstance(extra, dict):
            extra = {}
        extra["pdf_error"] = (error_message or "")[:500]
        if use_lock:
            cur.execute(
                """
                UPDATE radar_raw_document
                SET fetch_status = %s,
                    extra_json = %s,
                    content_locked_by = NULL,
                    content_locked_at = NULL,
                    updater = %s,
                    update_time = %s
                WHERE id = %s AND deleted = b'0'
                """,
                (
                    FETCH_FAILED,
                    json.dumps(extra, ensure_ascii=False),
                    settings.worker_id,
                    now,
                    doc_id,
                ),
            )
        else:
            cur.execute(
                """
                UPDATE radar_raw_document
                SET fetch_status = %s,
                    extra_json = %s,
                    updater = %s,
                    update_time = %s
                WHERE id = %s AND deleted = b'0'
                """,
                (
                    FETCH_FAILED,
                    json.dumps(extra, ensure_ascii=False),
                    settings.worker_id,
                    now,
                    doc_id,
                ),
            )
    conn.commit()


def update_document_content(
    conn: pymysql.Connection,
    settings: Settings,
    doc_id: int,
    *,
    content_text: str,
    content_hash_value: Optional[str],
    fetch_status: int,
    crawl_task_id: Optional[int] = None,
) -> None:
    """回填/更新证据正文，并释放租约锁（若有）。"""
    now = datetime.now()
    use_lock = _has_content_lock_columns(conn)
    with conn.cursor() as cur:
        if use_lock:
            cur.execute(
                """
                UPDATE radar_raw_document
                SET content_text = %s,
                    content_hash = %s,
                    fetch_status = %s,
                    crawl_task_id = COALESCE(%s, crawl_task_id),
                    content_locked_by = NULL,
                    content_locked_at = NULL,
                    updater = %s,
                    update_time = %s
                WHERE id = %s AND deleted = b'0'
                """,
                (
                    content_text,
                    content_hash_value,
                    fetch_status,
                    crawl_task_id,
                    settings.worker_id,
                    now,
                    doc_id,
                ),
            )
        else:
            cur.execute(
                """
                UPDATE radar_raw_document
                SET content_text = %s,
                    content_hash = %s,
                    fetch_status = %s,
                    crawl_task_id = COALESCE(%s, crawl_task_id),
                    updater = %s,
                    update_time = %s
                WHERE id = %s AND deleted = b'0'
                """,
                (
                    content_text,
                    content_hash_value,
                    fetch_status,
                    crawl_task_id,
                    settings.worker_id,
                    now,
                    doc_id,
                ),
            )
    conn.commit()
