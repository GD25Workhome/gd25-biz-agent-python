"""AnySearch 凭证池 / 动态配置的 DB 读写（exhibition MySQL）。

- 读：加载 key 行与配置类目（供 `pool` 组快照）。
- 写：租约、健康态、用量、重试日志（Phase 2/3 使用）。
- 兜底：DB 未配置/表为空时，用 `.env` 的 ANY_SEARCH_API_KEY(S) 作引导。
- 不含华院依赖。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import pymysql
from pymysql.cursors import DictCursor

from backend.app.config import settings

logger = logging.getLogger(__name__)

_KEY_TABLE = "radar_anysearch_key"
_CONFIG_TABLE = "radar_anysearch_config"
_NOT_DELETED = "deleted = b'0'"


def _connect() -> pymysql.connections.Connection:
    """
        建立 exhibition MySQL 连接（DictCursor，autocommit=False）。

        说明：slim 版删除了 `backend.infrastructure.database.mysql_connection`，
        这里用 `settings.require_exhibition_mysql()` + pymysql 自持短连接，
        保持与原 `query_all` / `execute` / `run_db` 同名同语义。

        Returns:
            pymysql 连接

        Raises:
            RuntimeError: 未配置 exhibition MySQL
    """
    params = settings.require_exhibition_mysql()
    return pymysql.connect(
        host=params["host"],
        port=params["port"],
        user=params["user"],
        password=params["password"],
        database=params["database"],
        charset=params.get("charset", "utf8mb4"),
        connect_timeout=params.get("connect_timeout", 10),
        cursorclass=DictCursor,
        autocommit=False,
    )


# 模块级薄封装：让下方代码沿用 query_all/execute/run_db 名字。
def query_all(sql: str, params=None):  # noqa: ANN001, ANN201
    """查询多行（短连接，DictCursor）。"""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()
    finally:
        conn.close()


def execute(sql: str, params=None):  # noqa: ANN001, ANN201
    """执行写入并提交（短连接）；返回受影响行数。"""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            affected = cur.execute(sql, params or [])
        conn.commit()
        return affected
    finally:
        conn.close()


async def run_db(fn, /, *args, **kwargs):  # noqa: ANN001, ANN201
    """把阻塞 DB 调用丢到线程执行，避免卡住事件循环。"""
    return await asyncio.to_thread(fn, *args, **kwargs)


# ---------------------------------------------------------------- 数据模型

@dataclass
class KeyRow:
    """radar_anysearch_key 的一行（仅池需要的字段）。"""

    id: int
    key_value: str
    key_label: str
    pool_tag: str
    enabled: bool
    health: str
    used_today: int
    daily_quota: int
    quota_date: Optional[date]
    max_qps: Optional[float]
    min_interval_ms: Optional[int]
    retry_log: str
    lease_until: Optional[datetime] = None
    lease_owner: Optional[str] = None


def sha1_hex(text: str) -> str:
    """key 的 sha1（唯一键/引用/日志）。"""
    return hashlib.sha1(str(text).encode("utf-8")).hexdigest()


def key_label(seq: int, key: str) -> str:
    """日志标识：#序号 …末4位（不泄露完整 key）。"""
    tail = key[-4:] if len(key) >= 4 else "****"
    return f"#{seq}…{tail}"


def _row_to_key(row: Dict[str, Any]) -> KeyRow:
    """DB 行 → KeyRow。"""
    raw_qps = row.get("max_qps")
    return KeyRow(
        id=int(row["id"]),
        key_value=str(row.get("key_value") or ""),
        key_label=str(row.get("key_label") or ""),
        pool_tag=str(row.get("pool_tag") or "shared"),
        enabled=bool(row.get("enabled")),
        health=str(row.get("health") or "available"),
        used_today=int(row.get("used_today") or 0),
        daily_quota=int(row.get("daily_quota") or 1000),
        quota_date=row.get("quota_date"),
        max_qps=float(raw_qps) if raw_qps is not None else None,
        min_interval_ms=(
            int(row["min_interval_ms"]) if row.get("min_interval_ms") is not None else None
        ),
        retry_log=str(row.get("retry_log") or ""),
        lease_until=row.get("lease_until"),
        lease_owner=row.get("lease_owner"),
    )


# ---------------------------------------------------------------- 读

def load_key_rows() -> List[KeyRow]:
    """
        读取可用的 key 行（enabled=1）。

        Returns:
            KeyRow 列表；DB 未配置/异常时返回空列表（由调用方回退 env）
    """
    if not settings.is_exhibition_mysql_enabled:
        return []
    sql = (
        "SELECT id, key_value, key_label, pool_tag, enabled, health, used_today, "
        "daily_quota, quota_date, max_qps, min_interval_ms, retry_log, lease_until, lease_owner "
        f"FROM {_KEY_TABLE} WHERE {_NOT_DELETED} AND enabled = 1"
    )
    try:
        return [_row_to_key(r) for r in query_all(sql)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("加载 AnySearch key 失败，回退 env: %s: %s", type(exc).__name__, exc)
        return []


def load_config_groups() -> Dict[str, Dict[str, Any]]:
    """
        读取配置类目：{类别: JSON 解析后的 dict}。

        Returns:
            类目字典；DB 未配置/异常时返回空 dict（由调用方用默认）
    """
    if not settings.is_exhibition_mysql_enabled:
        return {}
    sql = f"SELECT config_group, config_json FROM {_CONFIG_TABLE} WHERE {_NOT_DELETED}"
    out: Dict[str, Dict[str, Any]] = {}
    try:
        for row in query_all(sql):
            group = str(row.get("config_group") or "").strip()
            if not group:
                continue
            raw = row.get("config_json")
            try:
                obj = json.loads(raw) if raw else {}
            except Exception:  # noqa: BLE001
                obj = {}
            out[group] = obj if isinstance(obj, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("加载 AnySearch 配置失败，用默认: %s: %s", type(exc).__name__, exc)
        return {}
    return out


def version_probe() -> str:
    """
        轻量版本探测：两张表的 (MAX(update_time), COUNT(*)) 拼串。

        变了才需要全量重载（见 pool 的 TTL/探测）。

        Returns:
            版本串；DB 未配置/异常时返回空串
    """
    if not settings.is_exhibition_mysql_enabled:
        return ""
    try:
        parts: List[str] = []
        for table in (_KEY_TABLE, _CONFIG_TABLE):
            rows = query_all(
                f"SELECT COUNT(*) AS c, MAX(update_time) AS m FROM {table} WHERE {_NOT_DELETED}"
            )
            row = rows[0] if rows else {}
            parts.append(f"{row.get('c')}:{row.get('m')}")
        return "|".join(parts)
    except Exception:  # noqa: BLE001
        return ""


def env_seed_keys() -> List[str]:
    """
        从 `.env` 解析引导 key（池为空时的兜底）。

        Returns:
        去重后的 key 列表（不打印明文）
    """
    raw = getattr(settings, "ANY_SEARCH_API_KEYS", None) or ""
    keys: List[str] = [k.strip() for k in raw.split(",") if k.strip()] if raw else []
    if not keys:
        for name in ("ANY_SEARCH_API_KEY", "ANYSEARCH_API_KEY"):
            val = getattr(settings, name, None)
            if val and str(val).strip():
                keys.append(str(val).strip())
    seen: List[str] = []
    for k in keys:
        if k not in seen:
            seen.append(k)
    return seen


# ---------------------------------------------------------------- 写（Phase 2/3）

def claim_lease(key_id: int, owner: str, ttl_sec: int) -> bool:
    """
        原子抢租约（仅当 free/过期且 enabled+available）。

        Returns:
            是否抢到（rowcount==1）
    """
    sql = (
        f"UPDATE {_KEY_TABLE} SET lease_owner=%s, lease_until=DATE_ADD(NOW(), INTERVAL %s SECOND), "
        "updater=%s, update_time=NOW() "
        "WHERE id=%s AND enabled=1 AND health='available' AND " + _NOT_DELETED + " "
        "AND (lease_until IS NULL OR lease_until < NOW())"
    )
    return execute(sql, [owner, int(ttl_sec), owner, int(key_id)]) == 1


def renew_lease(key_id: int, owner: str, ttl_sec: int) -> int:
    """续租（仍由本 owner 持有才生效）。"""
    sql = (
        f"UPDATE {_KEY_TABLE} SET lease_until=DATE_ADD(NOW(), INTERVAL %s SECOND), update_time=NOW() "
        "WHERE id=%s AND lease_owner=%s AND " + _NOT_DELETED
    )
    return execute(sql, [int(ttl_sec), int(key_id), owner])


def release_lease(key_id: int, owner: str) -> int:
    """释放租约（仅本 owner）。"""
    sql = (
        f"UPDATE {_KEY_TABLE} SET lease_owner=NULL, lease_until=NULL, update_time=NOW() "
        "WHERE id=%s AND lease_owner=%s AND " + _NOT_DELETED
    )
    return execute(sql, [int(key_id), owner])


def mark_health(
    key_id: int,
    *,
    health: str,
    reason: Optional[str] = None,
    error_code: Optional[str] = None,
    cooldown_until: Optional[datetime] = None,
    success: bool = False,
) -> None:
    """回写健康态（异步调用见 `mark_health_async`）。"""
    now = datetime.now()
    if success:
        sql = (
            f"UPDATE {_KEY_TABLE} SET health=%s, health_reason=%s, fail_streak=0, "
            "last_ok_at=%s, last_used_at=%s, update_time=%s "
            "WHERE id=%s AND " + _NOT_DELETED
        )
        execute(sql, [health, (reason or "")[:200], now, now, now, int(key_id)])
        return
    sql = (
        f"UPDATE {_KEY_TABLE} SET health=%s, health_reason=%s, last_error_code=%s, "
        "last_error_msg=%s, fail_streak=fail_streak+1, last_fail_at=%s, last_used_at=%s, "
        "cooldown_until=%s, update_time=%s WHERE id=%s AND " + _NOT_DELETED
    )
    execute(
        sql,
        [
            health,
            (reason or "")[:200],
            error_code,
            (reason or "")[:500],
            now,
            now,
            cooldown_until,
            now,
            int(key_id),
        ],
    )


def bump_usage(key_id: int, n: int, today: date) -> None:
    """异步批量累加用量；跨日先归零（`quota_date != today`）。"""
    sql = (
        f"UPDATE {_KEY_TABLE} SET "
        "used_today = CASE WHEN quota_date = %s THEN used_today + %s ELSE %s END, "
        "quota_date = %s, update_time=NOW() WHERE id=%s AND " + _NOT_DELETED
    )
    execute(sql, [today, int(n), int(n), today, int(key_id)])


def append_retry_log(key_id: int, day: str, max_len: int) -> str:
    """
        追加一次「次日重试失败」日期，保留最近 max_len 条。

        Returns:
            新的 retry_log 字符串（JSON 数组）
    """
    rows = query_all(
        f"SELECT retry_log FROM {_KEY_TABLE} WHERE id=%s AND {_NOT_DELETED}",
        [int(key_id)],
    )
    raw = str(rows[0].get("retry_log") or "") if rows else ""
    try:
        arr = json.loads(raw) if raw else []
        arr = arr if isinstance(arr, list) else []
    except Exception:  # noqa: BLE001
        arr = []
    arr.append(str(day))
    arr = arr[-max(1, int(max_len)):]
    new = json.dumps(arr, ensure_ascii=False)
    execute(
        f"UPDATE {_KEY_TABLE} SET retry_log=%s, update_time=NOW() WHERE id=%s AND {_NOT_DELETED}",
        [new, int(key_id)],
    )
    return new


# ---------------------------------------------------------------- 异步门面

async def load_key_rows_async() -> List[KeyRow]:
    """`load_key_rows` 的异步版（线程池，不阻塞事件循环）。"""
    return await run_db(load_key_rows)


async def load_config_groups_async() -> Dict[str, Dict[str, Any]]:
    """`load_config_groups` 的异步版。"""
    return await run_db(load_config_groups)


async def version_probe_async() -> str:
    """`version_probe` 的异步版。"""
    return await run_db(version_probe)


async def claim_lease_async(key_id: int, owner: str, ttl_sec: int) -> bool:
    """`claim_lease` 的异步版。"""
    return await run_db(claim_lease, key_id, owner, ttl_sec)


async def release_lease_async(key_id: int, owner: str) -> int:
    """`release_lease` 的异步版。"""
    return await run_db(release_lease, key_id, owner)


async def mark_health_async(key_id: int, **kwargs: Any) -> None:
    """`mark_health` 的异步版（失败只告警，不影响请求路径）。"""
    try:
        await run_db(mark_health, key_id, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("回写 key 健康态失败 id=%s: %s", key_id, exc)


async def bump_usage_async(key_id: int, n: int, today: date) -> None:
    """`bump_usage` 的异步版（失败只告警）。"""
    try:
        await run_db(bump_usage, key_id, n, today)
    except Exception as exc:  # noqa: BLE001
        logger.warning("回写 key 用量失败 id=%s: %s", key_id, exc)


__all__ = [
    "KeyRow",
    "sha1_hex",
    "key_label",
    "load_key_rows",
    "load_key_rows_async",
    "load_config_groups",
    "load_config_groups_async",
    "version_probe",
    "version_probe_async",
    "env_seed_keys",
    "claim_lease",
    "claim_lease_async",
    "renew_lease",
    "release_lease",
    "release_lease_async",
    "mark_health",
    "mark_health_async",
    "bump_usage",
    "bump_usage_async",
    "append_retry_log",
]