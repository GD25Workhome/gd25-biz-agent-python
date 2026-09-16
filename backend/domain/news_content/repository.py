"""
雷达新闻知识库写链路的 MySQL 仓储（**只碰两张表**）。

    radar_news_content_task          抢锁 / 回写状态与结果（SELECT + UPDATE）
    radar_company_news_document      正文落库 / 向量状态回写 / 补跑扫描（SELECT + INSERT + UPDATE）

⚠️ 硬性边界
    - 其余 exhibition 表零接触（不读 `radar_company_news_url`、不读 `radar_company_source_url`，
      需要的字段全部来自 task 表快照）；
    - 不执行任何 DDL（建表归 exhibition Java SQL 脚本）；
    - 不碰 gd25 主库（PostgreSQL）。

⚠️ 为什么放在 domain 而不是 `infrastructure/database/repository/`
    那里是 SQLAlchemy `AsyncSession` + PG 的仓储（医疗线），本模块是 pymysql 直连 MySQL
    的另一条链路，混放会破坏两边的约定。连接与查询封装仍在
    `backend/infrastructure/database/mysql_connection.py`，这里只写 SQL。

⚠️ 并发语义（多实例靠 MySQL 行锁互斥，与巨潮线同构）
    抢锁 = `SELECT ... FOR UPDATE SKIP LOCKED` 拿 id 列表 → 条件
    `UPDATE ... WHERE status=0` → **校验 rowcount**，不等则整体回滚重来。
    只靠 UPDATE 的 `WHERE status=0` 也能防重，但拿不到「领到了哪几条」。

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md` §3.1 / §3.2 / §4.1 / §4.2
参照实现：exhibition_py/db/repository.py `claim_one_task` / `claim_docs_for_pdf`
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Optional

import pymysql

from backend.domain.news_content.constants import (
    EMBED_STATUS_FAILED,
    EMBED_STATUS_OK,
    EMBED_STATUS_PENDING,
    FETCH_STATUS_OK,
    TASK_STATUS_FAILED,
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SUCCESS,
)
from backend.infrastructure.database.mysql_connection import (
    execute,
    query_all,
    query_one,
    run_db,
    run_in_transaction,
)

logger = logging.getLogger(__name__)

# 业务侧一律用 `deleted = b'0'`（DDL 是 bit(1)，不是整数）
_NOT_DELETED = "deleted = b'0'"

# 列宽（与 DDL 对齐），写入前统一截断，避免 1406 Data too long 把整条任务打挂
_LEN_ERROR_MESSAGE = 1000
_LEN_TITLE_TASK = 512
_LEN_URL = 1024
_LEN_URL_NORM = 512
_LEN_CONTENT_SUMMARY = 1024
_LEN_PUBLISHED_AT = 32
_LEN_SOURCE_LEVEL = 8
_LEN_CHANNEL = 16
_LEN_AGENT_TRACE_ID = 64


def _truncate(value: Optional[str], limit: int) -> Optional[str]:
    """按列宽截断文本（None 透传）。"""
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[:limit]


def sha1_hex(text: Optional[str]) -> Optional[str]:
    """sha1 十六进制（`char(40)` 列用）。空文本返回 None。"""
    if not text:
        return None
    return hashlib.sha1(str(text).encode("utf-8")).hexdigest()


def normalize_content_for_hash(text: Optional[str]) -> Optional[str]:
    """
    正文哈希前的空白归一：与巨潮线 `repository.content_hash` 同口径（仅空白处理）。

    ⚠️ 只做空白归一，不做任何语义清洗 —— 原文改动即哈希变化，
    这正是 `content_hash` 作为「变更检测」的用途。
    """
    if not text:
        return None
    normalized = " ".join(str(text).split())
    return normalized or None


def content_sha1(text: Optional[str]) -> Optional[str]:
    """正文 sha1（空白归一再哈希，DDL 列宽 `char(40)`）。"""
    return sha1_hex(normalize_content_for_hash(text))


# ================================================================ task 表：抢锁

def _claim_tasks_sync(
    conn: pymysql.connections.Connection, worker_id: str, limit: int
) -> list[dict[str, Any]]:
    """
    同步抢锁实现（在单条连接、单个事务内完成）。

    步骤：
      1. `SELECT id ... FOR UPDATE SKIP LOCKED` —— 已被别的 worker 锁住的行直接跳过，
         不排队不阻塞（`SKIP LOCKED` 需 MySQL 8.0+，现网与巨潮线一致）
      2. 条件 `UPDATE ... WHERE status=0` 置 RUNNING 并盖 `locked_by/locked_at`
      3. **rowcount 必须等于领取条数**，否则回滚本次领取（可能有行被并发改掉）

    Returns:
        领取到的 task 行（status 已是 RUNNING）；没抢到返回 []
    """
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id FROM radar_news_content_task
            WHERE {_NOT_DELETED} AND status = %s
            ORDER BY id ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (TASK_STATUS_PENDING, int(limit)),
        )
        rows = list(cur.fetchall() or [])
        if not rows:
            conn.commit()
            return []

        task_ids = [int(r["id"]) for r in rows]
        placeholders = ",".join(["%s"] * len(task_ids))
        cur.execute(
            f"""
            UPDATE radar_news_content_task
            SET status = %s, locked_by = %s, locked_at = NOW(),
                updater = %s, update_time = NOW()
            WHERE status = %s AND {_NOT_DELETED} AND id IN ({placeholders})
            """,
            (TASK_STATUS_RUNNING, worker_id, worker_id, TASK_STATUS_PENDING, *task_ids),
        )
        affected = int(cur.rowcount or 0)
        if affected != len(task_ids):
            # 有行在 SELECT 与 UPDATE 之间被改掉 —— 整体放弃，下一轮再抢
            logger.warning(
                "抢锁 rowcount 不一致（期望 %d 实际 %d），本轮放弃", len(task_ids), affected
            )
            conn.rollback()
            return []

        cur.execute(
            f"""
            SELECT * FROM radar_news_content_task
            WHERE id IN ({placeholders}) AND locked_by = %s AND status = %s
            ORDER BY id ASC
            """,
            (*task_ids, worker_id, TASK_STATUS_RUNNING),
        )
        claimed = list(cur.fetchall() or [])
    conn.commit()
    logger.info("领取任务 worker=%s count=%d ids=%s", worker_id, len(claimed), task_ids)
    return claimed


async def claim_tasks(worker_id: str, limit: int) -> list[dict[str, Any]]:
    """
    抢一批 PENDING 任务（异步门面）。

    Args:
        worker_id: 实例标识（写 `locked_by`）
        limit: 本轮最多领取条数（N）

    Returns:
        已置为 RUNNING 的 task 行；无任务返回 []
    """
    if limit <= 0:
        return []
    return await run_db(run_in_transaction, _claim_tasks_sync, worker_id, int(limit))


async def reset_stale_running(timeout_seconds: int) -> int:
    """
    把超时未回写的 RUNNING 任务重置回 PENDING（worker 挂死自愈）。

    与设计文档 §8-12 一致：进程挂掉的任务经 RUNNING 超时重置自动恢复。
    同时清空 `locked_by/locked_at`，让任务可被任何实例重新领取。

    ⚠️ 重置 = 重跑（重跑 Agent = 花钱），因此超时值不宜过小；
    默认 1800s（30 分钟），见 `NEWS_CONTENT_LOCK_TIMEOUT_SECONDS`。

    Args:
        timeout_seconds: `locked_at` 早于「现在 - 本值」的 RUNNING 任务会被重置

    Returns:
        实际重置条数
    """
    return await run_db(
        execute,
        f"""
        UPDATE radar_news_content_task
        SET status = %s, locked_by = NULL, locked_at = NULL, update_time = NOW()
        WHERE status = %s AND {_NOT_DELETED}
          AND (locked_at IS NULL OR locked_at < DATE_SUB(NOW(), INTERVAL %s SECOND))
        """,
        (TASK_STATUS_PENDING, TASK_STATUS_RUNNING, int(timeout_seconds)),
    )


# ================================================================ task 表：回写

async def mark_task_success(
    task_id: int,
    *,
    worker_id: str,
    document_id: Optional[int],
    actual_channel: str,
    title: Optional[str] = None,
    published_at: Optional[str] = None,
    content_hash: Optional[str] = None,
    embed_status: Optional[int] = None,
    cost_ms: Optional[int] = None,
    agent_trace_id: Optional[str] = None,
) -> None:
    """
    任务成功回写。

    Args:
        task_id: 任务编号
        worker_id: 实例标识（写 updater）
        document_id: 落库的 document.id
        actual_channel: 实际执行通道 rule / agent（结果字段，供判据 A 统计）
        title / published_at / content_hash: 出参摘要（与 document 表一致）
        embed_status: 冗余向量化状态（权威值在 document 表；None 表示不变）
        cost_ms: 本任务耗时毫秒
        agent_trace_id: Agent 兜底通道的 trace_id
    """
    await run_db(
        execute,
        f"""
        UPDATE radar_news_content_task
        SET status = %s, actual_channel = %s, document_id = %s,
            title = %s, published_at = %s, content_hash = %s,
            embed_status = COALESCE(%s, embed_status),
            cost_ms = %s, agent_trace_id = %s, error_message = NULL,
            locked_by = NULL, locked_at = NULL, updater = %s, update_time = NOW()
        WHERE id = %s AND {_NOT_DELETED}
        """,
        (
            TASK_STATUS_SUCCESS,
            _truncate(actual_channel, _LEN_CHANNEL),
            document_id,
            _truncate(title, _LEN_TITLE_TASK),
            _truncate(published_at, _LEN_PUBLISHED_AT),
            content_hash,
            embed_status,
            cost_ms,
            _truncate(agent_trace_id, _LEN_AGENT_TRACE_ID),
            worker_id,
            int(task_id),
        ),
    )


async def mark_task_failed(
    task_id: int,
    *,
    worker_id: str,
    error_message: Optional[str],
    actual_channel: Optional[str] = None,
    embed_status: Optional[int] = None,
    cost_ms: Optional[int] = None,
    agent_trace_id: Optional[str] = None,
) -> None:
    """
    任务失败回写（**默认不自动重试**，由人工在运维台重置为 PENDING）。

    ⚠️ 分步记状态：`embed_status` 只在**向量段失败**时传，
    下载失败只落 `error_message`，两者互不覆盖。
    """
    await run_db(
        execute,
        f"""
        UPDATE radar_news_content_task
        SET status = %s, actual_channel = COALESCE(%s, actual_channel),
            error_message = %s, embed_status = COALESCE(%s, embed_status),
            cost_ms = %s, agent_trace_id = %s,
            locked_by = NULL, locked_at = NULL, updater = %s, update_time = NOW()
        WHERE id = %s AND {_NOT_DELETED}
        """,
        (
            TASK_STATUS_FAILED,
            _truncate(actual_channel, _LEN_CHANNEL) if actual_channel else None,
            _truncate(error_message, _LEN_ERROR_MESSAGE),
            embed_status,
            cost_ms,
            _truncate(agent_trace_id, _LEN_AGENT_TRACE_ID),
            worker_id,
            int(task_id),
        ),
    )


async def update_task_embed_status(task_id: int, embed_status: int, worker_id: str) -> None:
    """只更新 task 的冗余 `embed_status`（补跑循环用，不动 status）。"""
    await run_db(
        execute,
        f"""
        UPDATE radar_news_content_task
        SET embed_status = %s, updater = %s, update_time = NOW()
        WHERE id = %s AND {_NOT_DELETED}
        """,
        (int(embed_status), worker_id, int(task_id)),
    )


async def update_task_document_id(task_id: int, document_id: int, worker_id: str) -> None:
    """只回填 task 的 `document_id`（下载失败写入占位行后，供运维台跳转）。"""
    await run_db(
        execute,
        f"""
        UPDATE radar_news_content_task
        SET document_id = %s, updater = %s, update_time = NOW()
        WHERE id = %s AND {_NOT_DELETED}
        """,
        (int(document_id), worker_id, int(task_id)),
    )


# ================================================================ document 表

def _document_upsert_sync(
    conn: pymysql.connections.Connection, doc: dict[str, Any], worker_id: str
) -> int:
    """
    同步 upsert 实现：`uk(news_url_id, deleted)` 命中则 UPDATE，否则 INSERT。

    ⚠️ 不用 `INSERT ... ON DUPLICATE KEY UPDATE`：`VALUES()` 形式在 MySQL 8.0.20+
    已废弃、9.x 移除，跨版本不稳；这里显式「先 SELECT FOR UPDATE 再分流」，
    并在并发撞唯一键时兜底重试一次 UPDATE，语义等价且版本无关。

    Returns:
        document.id（新增或既有的）
    """
    news_url_id = int(doc["news_url_id"])
    now = datetime.now()
    url_norm = _truncate(doc.get("url_norm"), _LEN_URL_NORM) or ""
    url_hash = doc.get("url_hash") or sha1_hex(url_norm) or ""
    values: dict[str, Any] = {
        "company_id": int(doc["company_id"]),
        "news_url_id": news_url_id,
        "source_url_id": int(doc["source_url_id"]),
        "title": _truncate(doc.get("title"), _LEN_TITLE_TASK),
        "url": _truncate(doc.get("url"), _LEN_URL),
        "url_norm": url_norm,
        "url_hash": url_hash,
        "published_at": _truncate(doc.get("published_at"), _LEN_PUBLISHED_AT),
        "content_text": doc.get("content_text"),
        "content_summary": _truncate(doc.get("content_summary"), _LEN_CONTENT_SUMMARY),
        "content_hash": doc.get("content_hash"),
        "source_type": _truncate(doc.get("source_type"), _LEN_CHANNEL) or "rule",
        "source_level": _truncate(doc.get("source_level"), _LEN_SOURCE_LEVEL) or "P0",
        "fetch_status": int(doc.get("fetch_status", 1)),
        "embed_status": int(doc.get("embed_status", EMBED_STATUS_PENDING)),
        "vector_id": doc.get("vector_id"),
        "extra_json": doc.get("extra_json"),
        "tenant_id": int(doc.get("tenant_id") or 0),
    }
    assignments = ", ".join(f"{k} = %s" for k in values)
    columns = ", ".join(values.keys())
    placeholders = ", ".join(["%s"] * len(values))

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id FROM radar_company_news_document
            WHERE news_url_id = %s AND {_NOT_DELETED}
            FOR UPDATE
            """,
            (news_url_id,),
        )
        existing = cur.fetchone()

        if existing:
            doc_id = int(existing["id"])
            cur.execute(
                f"""
                UPDATE radar_company_news_document
                SET {assignments}, updater = %s, update_time = %s
                WHERE id = %s
                """,
                (*values.values(), worker_id, now, doc_id),
            )
        else:
            try:
                cur.execute(
                    f"""
                    INSERT INTO radar_company_news_document
                        ({columns}, creator, create_time, updater, update_time, deleted)
                    VALUES ({placeholders}, %s, %s, %s, %s, b'0')
                    """,
                    (*values.values(), worker_id, now, worker_id, now),
                )
                doc_id = int(cur.lastrowid or 0)
            except pymysql.err.IntegrityError:
                # 并发下另一个实例刚插入同 news_url_id —— 退化为 UPDATE
                conn.rollback()
                cur.execute(
                    f"""
                    SELECT id FROM radar_company_news_document
                    WHERE news_url_id = %s AND {_NOT_DELETED}
                    """,
                    (news_url_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise
                doc_id = int(row["id"])
                cur.execute(
                    f"""
                    UPDATE radar_company_news_document
                    SET {assignments}, updater = %s, update_time = %s
                    WHERE id = %s
                    """,
                    (*values.values(), worker_id, now, doc_id),
                )
    conn.commit()
    return doc_id


async def upsert_document(doc: dict[str, Any], worker_id: str) -> int:
    """
    写入/更新一篇新闻正文（一 URL 一篇，幂等）。

    Args:
        doc: 字段见 `_document_upsert_sync`；必填
             company_id / news_url_id / source_url_id / url / url_norm
             （`url_hash`/`content_hash` 缺省时按 url_norm / content_text 现算）
        worker_id: 实例标识（写 creator/updater）

    Returns:
        document.id
    """
    return await run_db(run_in_transaction, _document_upsert_sync, doc, worker_id)


async def mark_document_embed_ok(
    doc_id: int, *, worker_id: str, vector_id: int
) -> None:
    """向量化成功回写：`embed_status=1` + `vector_id`（Milvus 主键）。"""
    await run_db(
        execute,
        f"""
        UPDATE radar_company_news_document
        SET embed_status = %s, vector_id = %s, updater = %s, update_time = NOW()
        WHERE id = %s AND {_NOT_DELETED}
        """,
        (EMBED_STATUS_OK, int(vector_id), worker_id, int(doc_id)),
    )


def _mark_document_embed_failed_sync(
    conn: pymysql.connections.Connection,
    doc_id: int,
    worker_id: str,
    error_message: Optional[str],
) -> int:
    """
    同步实现：置 `embed_status=2`，并在 `extra_json.embed_attempts` 累加尝试次数。

    为什么要计数：补跑循环每轮都会扫到 `embed_status=2`，
    没有上限的话一篇永久失败的文档会无限重试、持续消耗网关配额；
    累计到 `NEWS_CONTENT_EMBED_MAX_ATTEMPTS` 后保持 2 不再重试（终态）。

    Returns:
        累加后的尝试次数
    """
    now = datetime.now()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT extra_json FROM radar_company_news_document
            WHERE id = %s AND {_NOT_DELETED} FOR UPDATE
            """,
            (int(doc_id),),
        )
        row = cur.fetchone()
        if not row:
            conn.commit()
            return 0

        extra: dict[str, Any] = {}
        raw_extra = row.get("extra_json")
        if raw_extra:
            try:
                parsed = json.loads(raw_extra)
                if isinstance(parsed, dict):
                    extra = parsed
            except (TypeError, ValueError):
                # 历史脏数据：整段替换，不让脏 JSON 阻断补跑
                extra = {}
        attempts = int(extra.get("embed_attempts") or 0) + 1
        extra["embed_attempts"] = attempts
        extra["embed_error"] = _truncate(error_message, 500)
        extra["embed_failed_at"] = now.strftime("%Y-%m-%d %H:%M:%S")

        cur.execute(
            f"""
            UPDATE radar_company_news_document
            SET embed_status = %s, extra_json = %s, updater = %s, update_time = %s
            WHERE id = %s
            """,
            (
                EMBED_STATUS_FAILED,
                json.dumps(extra, ensure_ascii=False),
                worker_id,
                now,
                int(doc_id),
            ),
        )
    conn.commit()
    return attempts


async def mark_document_embed_failed(
    doc_id: int, *, worker_id: str, error_message: Optional[str]
) -> int:
    """
    向量化失败回写（`embed_status=2`），返回累计尝试次数。

    ⚠️ 只动 `embed_status` 与 `extra_json`，**不覆盖 `fetch_status`**：
    下载成功的正文保留，补跑只重做向量段。
    """
    return await run_db(
        run_in_transaction, _mark_document_embed_failed_sync, doc_id, worker_id, error_message
    )


def parse_embed_attempts(extra_json: Any) -> int:
    """从 `extra_json` 里取已尝试的 embedding 次数（脏数据按 0 处理）。"""
    if not extra_json:
        return 0
    try:
        parsed = json.loads(extra_json) if isinstance(extra_json, str) else extra_json
    except (TypeError, ValueError):
        return 0
    if not isinstance(parsed, dict):
        return 0
    try:
        return int(parsed.get("embed_attempts") or 0)
    except (TypeError, ValueError):
        return 0


def _mark_document_fetch_failed_sync(
    conn: pymysql.connections.Connection, doc: dict[str, Any], worker_id: str
) -> Optional[int]:
    """
    同步实现：下载彻底失败（规则 + Agent 都没抓到）时占位一行 `fetch_status=2`。

    为什么要占位：
      1. 判据 A 要「按站点统计 `fetch_status=2` 分布」识别不可抓站点 —— 没有行就没法统计；
      2. exhibition 建任务的扫描条件是「news_url 无对应 document 且无活跃 task」，
         不留占位行的话失败 URL 会被反复建任务（重跑 = 重跑 Agent = 花钱）。
         设计已明确「默认不自动重试」，失败由人工在运维台重置。

    ⚠️ **已存在则不覆盖**：不把已有的正文/状态改坏（例如任务被人工重置后重跑又失败）。

    Returns:
        占位 document.id；已存在则返回既有 id
    """

    def _tx(inner_conn: pymysql.connections.Connection) -> Optional[int]:
        news_url_id = int(doc["news_url_id"])
        now = datetime.now()
        with inner_conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id FROM radar_company_news_document
                WHERE news_url_id = %s AND {_NOT_DELETED}
                FOR UPDATE
                """,
                (news_url_id,),
            )
            existing = cur.fetchone()
            if existing:
                inner_conn.commit()
                return int(existing["id"])

            url_norm = _truncate(doc.get("url_norm"), _LEN_URL_NORM) or ""
            cur.execute(
                f"""
                INSERT INTO radar_company_news_document
                    (company_id, news_url_id, source_url_id, title, url, url_norm, url_hash,
                     published_at, content_text, content_summary, content_hash,
                     source_type, source_level, fetch_status, embed_status,
                     extra_json, creator, create_time, updater, update_time, deleted, tenant_id)
                VALUES (%s, %s, %s, NULL, %s, %s, %s,
                        NULL, NULL, NULL, NULL,
                        %s, %s, 2, 0,
                        %s, %s, %s, %s, %s, b'0', %s)
                """,
                (
                    int(doc["company_id"]),
                    news_url_id,
                    int(doc["source_url_id"]),
                    _truncate(doc.get("url"), _LEN_URL),
                    url_norm,
                    sha1_hex(url_norm) or "",
                    _truncate(doc.get("source_type"), _LEN_CHANNEL) or "rule",
                    _truncate(doc.get("source_level"), _LEN_SOURCE_LEVEL) or "P0",
                    doc.get("extra_json"),
                    worker_id, now, worker_id, now,
                    int(doc.get("tenant_id") or 0),
                ),
            )
            doc_id = int(cur.lastrowid or 0)
        inner_conn.commit()
        return doc_id

    return _tx(conn)


async def mark_document_fetch_failed(doc: dict[str, Any], worker_id: str) -> Optional[int]:
    """
    下载彻底失败时的 document 占位写入（`fetch_status=2`，已存在则不覆盖）。

    Args:
        doc: 至少含 company_id / news_url_id / source_url_id / url / url_norm / source_level
        worker_id: 实例标识

    Returns:
        占位行 id
    """
    return await run_db(run_in_transaction, _mark_document_fetch_failed_sync, doc, worker_id)


async def find_task_by_document_id(doc_id: int) -> Optional[dict[str, Any]]:
    """
    按 `document_id` 反查最近一条 task（补跑循环回写冗余 `embed_status` 用）。

    ⚠️ 只读 task 表，符合「只碰两张表」的边界。
    """
    return await run_db(
        query_one,
        f"""
        SELECT id, embed_status FROM radar_news_content_task
        WHERE document_id = %s AND {_NOT_DELETED}
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(doc_id),),
    )


# ================================================================ 只读查询（补跑 / 自检）

async def list_documents_for_embed_backfill(limit: int, max_attempts: int = 3) -> list[dict[str, Any]]:
    """
    补跑扫描：取一批「正文已抓但向量未就绪」的 document。

    条件：`fetch_status=1`（正文在库，**不重复下载**）+ `embed_status IN (0, 2)`
    （待向量化 / 曾失败）。用 `IN` 而不是 `<> 1` 是为了命中 `idx_embed_status`。

    ⚠️ 达重试上限（`extra_json.embed_attempts >= max_attempts`）的文档必须在
    **SQL 层**过滤掉：若只在 Python 层 skip，`ORDER BY id ASC LIMIT n` 每轮
    都取回同一批「已达上限」的文档，后面的待补跑文档永远轮不到（死循环）。
    """
    return await run_db(
        query_all,
        f"""
        SELECT id, company_id, news_url_id, source_url_id, title, url, url_norm,
               published_at, content_text, content_summary, content_hash,
               embed_status, extra_json
        FROM radar_company_news_document
        WHERE {_NOT_DELETED}
          AND fetch_status = %s
          AND embed_status IN (%s, %s)
          AND content_text IS NOT NULL AND content_text <> ''
          AND (
              extra_json IS NULL OR extra_json = ''
              OR COALESCE(CAST(JSON_EXTRACT(extra_json, '$.embed_attempts') AS UNSIGNED), 0) < %s
          )
        ORDER BY id ASC
        LIMIT %s
        """,
        (FETCH_STATUS_OK, EMBED_STATUS_PENDING, EMBED_STATUS_FAILED, int(max_attempts), int(limit)),
    )


async def get_document(doc_id: int) -> Optional[dict[str, Any]]:
    """按主键取一篇 document（联调/自检用）。"""
    return await run_db(
        query_one,
        f"SELECT * FROM radar_company_news_document WHERE id = %s AND {_NOT_DELETED}",
        (int(doc_id),),
    )


async def get_task(task_id: int) -> Optional[dict[str, Any]]:
    """按主键取一条 task（联调/自检用）。"""
    return await run_db(
        query_one,
        f"SELECT * FROM radar_news_content_task WHERE id = %s AND {_NOT_DELETED}",
        (int(task_id),),
    )


async def count_tasks_by_status() -> dict[int, int]:
    """
    按状态统计任务数（**只读**，worker `--dry-run` 自检用）。

    Returns:
        {status: count}，只含表里出现过的状态
    """
    rows = await run_db(
        query_all,
        f"""
        SELECT status, COUNT(*) AS cnt FROM radar_news_content_task
        WHERE {_NOT_DELETED}
        GROUP BY status
        """,
    )
    return {int(r["status"]): int(r["cnt"]) for r in rows}


async def list_pending_tasks_preview(limit: int) -> list[dict[str, Any]]:
    """只读预览 PENDING 任务（**不改状态、不抢锁**，`--dry-run` 自检用）。"""
    return await run_db(
        query_all,
        f"""
        SELECT id, company_id, news_url_id, source_url_id, source_level, url,
               company_name, stock_code, status, locked_by, create_time
        FROM radar_news_content_task
        WHERE {_NOT_DELETED} AND status = %s
        ORDER BY id ASC
        LIMIT %s
        """,
        (TASK_STATUS_PENDING, int(limit)),
    )


async def count_documents_by_embed_status() -> dict[int, int]:
    """按 `embed_status` 统计 document 数（只读，自检/验收用）。"""
    rows = await run_db(
        query_all,
        f"""
        SELECT embed_status, COUNT(*) AS cnt FROM radar_company_news_document
        WHERE {_NOT_DELETED}
        GROUP BY embed_status
        """,
    )
    return {int(r["embed_status"]): int(r["cnt"]) for r in rows}


async def fetch_status_distribution_by_source() -> list[dict[str, Any]]:
    """按信息源统计 `fetch_status` 分布（判据 A「不可抓站点清单」，只读）。"""
    return await run_db(
        query_all,
        f"""
        SELECT source_url_id, fetch_status, COUNT(*) AS cnt
        FROM radar_company_news_document
        WHERE {_NOT_DELETED}
        GROUP BY source_url_id, fetch_status
        ORDER BY source_url_id ASC, fetch_status ASC
        """,
    )


__all__ = [
    "claim_tasks",
    "reset_stale_running",
    "mark_task_success",
    "mark_task_failed",
    "update_task_embed_status",
    "update_task_document_id",
    "upsert_document",
    "mark_document_fetch_failed",
    "mark_document_embed_ok",
    "mark_document_embed_failed",
    "find_task_by_document_id",
    "parse_embed_attempts",
    "list_documents_for_embed_backfill",
    "get_document",
    "get_task",
    "count_tasks_by_status",
    "list_pending_tasks_preview",
    "count_documents_by_embed_status",
    "fetch_status_distribution_by_source",
    "content_sha1",
    "sha1_hex",
    "normalize_content_for_hash",
]
