"""
画像 / 展厅需求任务的认领与超时退回。

互斥条件与 Java 手动入队一致：只有 status=0 的行能被改成 RUNNING。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from radar_score.config import EVENT_KIND, JOB_KINDS, PROFILE_KIND, ScoreSettings

log = logging.getLogger("radar_score.repository")

STATUS_PENDING = 0
STATUS_RUNNING = 1
STATUS_FAILED = 3

_NOT_DELETED = "deleted = b'0'"
_TABLES = {
    PROFILE_KIND: "radar_profile_job",
    EVENT_KIND: "radar_event_job",
}
_RECLAIM_MESSAGE = "RUNNING 超时，退回待执行"


def table_of(kind: str) -> str:
    """
        任务类型对应的表名。

        Args:
            kind: profile 或 event

        Returns:
            表名

        Raises:
            ValueError: 未知类型
    """
    try:
        return _TABLES[kind]
    except KeyError as ex:
        raise ValueError(f"未知评分任务类型: {kind}") from ex


def connect(settings: ScoreSettings) -> pymysql.Connection:
    """
        创建 MySQL 连接。

        Args:
            settings: 调度配置

        Returns:
            关闭自动提交的连接
    """
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


def _tenant_clause(settings: ScoreSettings) -> tuple[str, list[Any]]:
    if settings.tenant_id is None:
        return "", []
    return " AND tenant_id = %s", [settings.tenant_id]


def reclaim_stale(conn: pymysql.Connection, settings: ScoreSettings) -> int:
    """
        把超时仍为 RUNNING 的任务退回 PENDING。

        java-manual 与 python-score- 都回收，避免任一侧认领后进程退出导致任务永远停住。

        Args:
            conn: 数据库连接
            settings: 调度配置

        Returns:
            退回条数
    """
    deadline = datetime.now() - timedelta(seconds=settings.stale_timeout_sec)
    now = datetime.now()
    tenant_sql, tenant_params = _tenant_clause(settings)
    total = 0
    with conn.cursor() as cur:
        for kind in JOB_KINDS:
            table = table_of(kind)
            cur.execute(
                f"""
                UPDATE {table}
                SET status = %s,
                    locked_by = NULL,
                    locked_at = NULL,
                    error_message = %s,
                    updater = %s,
                    update_time = %s
                WHERE status = %s
                  AND locked_at IS NOT NULL
                  AND locked_at < %s
                  AND {_NOT_DELETED}{tenant_sql}
                """,
                [
                    STATUS_PENDING,
                    _RECLAIM_MESSAGE,
                    settings.locked_by,
                    now,
                    STATUS_RUNNING,
                    deadline,
                    *tenant_params,
                ],
            )
            total += int(cur.rowcount or 0)
    conn.commit()
    if total:
        log.warning("超时退回 PENDING %s 条", total)
    return total


def claim_jobs(
    conn: pymysql.Connection,
    settings: ScoreSettings,
    kind: str,
    limit: int,
) -> list[int]:
    """
        认领至多 limit 条 PENDING 任务。

        Args:
            conn: 数据库连接
            settings: 调度配置
            kind: profile 或 event
            limit: 本轮最多条数

        Returns:
            已置为 RUNNING 的任务 id
    """
    n = int(limit)
    if n <= 0:
        return []
    table = table_of(kind)
    tenant_sql, tenant_params = _tenant_clause(settings)
    claimed: list[int] = []
    now = datetime.now()
    with conn.cursor() as cur:
        # 1. 锁住本批待执行行，跳过已被其它事务锁住的
        cur.execute(
            f"""
            SELECT id
            FROM {table}
            WHERE {_NOT_DELETED} AND status = %s{tenant_sql}
            ORDER BY id ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            [STATUS_PENDING, *tenant_params, n],
        )
        rows = list(cur.fetchall() or [])
        # 2. 条件更新：只有仍是 PENDING 的才算领到
        for row in rows:
            job_id = int(row["id"])
            cur.execute(
                f"""
                UPDATE {table}
                SET status = %s,
                    locked_by = %s,
                    locked_at = %s,
                    updater = %s,
                    update_time = %s
                WHERE id = %s AND status = %s AND {_NOT_DELETED}
                """,
                (
                    STATUS_RUNNING,
                    settings.locked_by,
                    now,
                    settings.locked_by,
                    now,
                    job_id,
                    STATUS_PENDING,
                ),
            )
            if cur.rowcount == 1:
                claimed.append(job_id)
    conn.commit()
    if claimed:
        log.info("认领 %s %s", kind, claimed)
    return claimed


def next_status(retryable: bool, retry_count: int, max_retry: int) -> int:
    """
        失败后任务应置的状态（纯函数，便于单测）。

        可重试异常且未达重试上限 → PENDING（等下一轮重试）；
        否则 → FAILED（记录原因、停止循环，避免任务卡住反复重跑）。

        Args:
            retryable: 异常是否属于可重试（网络/依赖抖动）
            retry_count: 本次失败前已重试次数
            max_retry: 允许的最大重试次数

        Returns:
            STATUS_PENDING 或 STATUS_FAILED
    """
    if retryable and (int(retry_count) + 1) <= int(max_retry):
        return STATUS_PENDING
    return STATUS_FAILED


def release_claim(
    conn: pymysql.Connection,
    settings: ScoreSettings,
    kind: str,
    job_id: int,
    reason: str,
    *,
    retryable: bool = True,
) -> int:
    """
        执行失败后处置本进程认领的任务。

        确定性错误（数据/结构不合规）或超过重试上限 → FAILED 并写 error_message；
        可重试错误且未超上限 → 退回 PENDING，等下一轮重试。
        两种情形都记录失败原因，避免任务静默卡在 PENDING 反复重跑。

        Args:
            conn: 数据库连接
            settings: 调度配置
            kind: profile 或 event
            job_id: 任务编号
            reason: 写回 error_message 的说明
            retryable: 是否可重试（默认 True）

        Returns:
            处置后的状态码（STATUS_PENDING / STATUS_FAILED）
    """
    table = table_of(kind)
    now = datetime.now()
    message = (reason or "执行失败")[:900]
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT retry_count FROM {table} "
            f"WHERE id = %s AND status = %s AND locked_by = %s AND {_NOT_DELETED}",
            [int(job_id), STATUS_RUNNING, settings.locked_by],
        )
        row = cur.fetchone()
        if row is None:
            conn.commit()
            return STATUS_FAILED
        status = next_status(retryable, int(row.get("retry_count") or 0), settings.max_retry)
        cur.execute(
            f"""
            UPDATE {table}
            SET status = %s,
                retry_count = retry_count + 1,
                locked_by = NULL,
                locked_at = NULL,
                error_message = %s,
                updater = %s,
                update_time = %s
            WHERE id = %s AND status = %s AND locked_by = %s AND {_NOT_DELETED}
            """,
            (
                status,
                message,
                settings.locked_by,
                now,
                int(job_id),
                STATUS_RUNNING,
                settings.locked_by,
            ),
        )
    conn.commit()
    if status == STATUS_FAILED:
        log.error("任务标记失败 kind=%s jobId=%s reason=%s", kind, job_id, message)
    else:
        log.warning("退回 PENDING 待重试 kind=%s jobId=%s reason=%s", kind, job_id, message)
    return status
