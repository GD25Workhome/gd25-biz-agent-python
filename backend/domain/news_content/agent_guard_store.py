"""
Agent 兜底闸门持久化（`radar_news_agent_guard`）。

设计文档：`ai_docs/26091605-Agent兜底闸门改造设计.md` §6

两类行：
    GLOBAL（guard_scope=0, source_url_id=0）—— 日配额 / 系统熔断
    SOURCE（guard_scope=1, source_url_id>0）—— 按信息源内容跳过

提供：
    - MysqlAgentGuardStore：exhibition MySQL 权威实现
    - InMemoryAgentGuardStore：单测 / 无库时的进程内实现（语义对齐）
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional, Protocol
from zoneinfo import ZoneInfo

import pymysql
from pymysql.err import IntegrityError

from backend.infrastructure.database.mysql_connection import run_db, run_in_transaction

logger = logging.getLogger(__name__)

GUARD_SCOPE_GLOBAL = 0
GUARD_SCOPE_SOURCE = 1
_NOT_DELETED = "deleted = b'0'"
_STAT_TZ = ZoneInfo("Asia/Shanghai")


def today_stat_date() -> date:
    """闸门统计日（Asia/Shanghai 日历日）。"""
    return datetime.now(_STAT_TZ).date()


class AgentGuardStore(Protocol):
    """闸门状态存储协议（MySQL / 内存实现共用）。"""

    async def is_system_tripped(self, stat_date: date) -> bool:
        """当日全局是否已系统熔断。"""
        ...

    async def is_source_skipped(self, source_url_id: int, stat_date: date) -> bool:
        """该信息源当日是否已跳过 Agent。"""
        ...

    async def try_consume_quota(
        self, stat_date: date, daily_quota: int
    ) -> tuple[bool, int, str]:
        """
            原子扣减日配额。

            Returns:
                (是否成功, 扣减后 used, 失败原因)
        """
        ...

    async def mark_system_result(
        self, stat_date: date, *, success: bool, max_streak: int
    ) -> bool:
        """
            记录系统侧结果。

            Returns:
                是否已触发 system_tripped
        """
        ...

    async def mark_content_result(
        self,
        source_url_id: int,
        stat_date: date,
        *,
        success: bool,
        increment_streak: bool,
        max_streak: int,
    ) -> bool:
        """
            记录该信息源内容侧结果。

            Args:
                increment_streak: False 时仅表示 content 失败但不推 skip（临时故障）

            Returns:
                是否已 content_skipped
        """
        ...


# ================================================================ MySQL

def _select_row_sync(
    cur: Any,
    *,
    guard_scope: int,
    source_url_id: int,
    stat_date: date,
    for_update: bool = False,
) -> Optional[dict[str, Any]]:
    """按唯一键读一行。"""
    lock = " FOR UPDATE" if for_update else ""
    cur.execute(
        f"""
        SELECT id, guard_scope, source_url_id, stat_date,
               agent_used, system_fail_streak, system_tripped,
               content_fail_streak, content_skipped, version
        FROM radar_news_agent_guard
        WHERE guard_scope = %s AND source_url_id = %s AND stat_date = %s
          AND {_NOT_DELETED}
        {lock}
        """,
        (guard_scope, source_url_id, stat_date),
    )
    return cur.fetchone()


def _insert_row_sync(
    cur: Any,
    *,
    guard_scope: int,
    source_url_id: int,
    stat_date: date,
) -> None:
    """插入空行；冲突由调用方处理。"""
    cur.execute(
        f"""
        INSERT INTO radar_news_agent_guard
            (guard_scope, source_url_id, stat_date,
             agent_used, system_fail_streak, system_tripped,
             content_fail_streak, content_skipped, version,
             deleted)
        VALUES (%s, %s, %s, 0, 0, 0, 0, 0, 0, b'0')
        """,
        (guard_scope, source_url_id, stat_date),
    )


def _ensure_row_locked_sync(
    conn: pymysql.connections.Connection,
    *,
    guard_scope: int,
    source_url_id: int,
    stat_date: date,
) -> dict[str, Any]:
    """
        确保行存在并以 FOR UPDATE 锁住后返回。

        并发双插：捕获 IntegrityError 后重新 SELECT FOR UPDATE。
    """
    with conn.cursor() as cur:
        # 1. 先试读加锁
        row = _select_row_sync(
            cur,
            guard_scope=guard_scope,
            source_url_id=source_url_id,
            stat_date=stat_date,
            for_update=True,
        )
        if row:
            return row

        # 2. 不存在则插入
        try:
            _insert_row_sync(
                cur,
                guard_scope=guard_scope,
                source_url_id=source_url_id,
                stat_date=stat_date,
            )
        except IntegrityError:
            # 并发双插：对方已插入，改为锁读
            pass

        row = _select_row_sync(
            cur,
            guard_scope=guard_scope,
            source_url_id=source_url_id,
            stat_date=stat_date,
            for_update=True,
        )
        if not row:
            raise RuntimeError(
                f"radar_news_agent_guard 行创建失败 scope={guard_scope} "
                f"source_url_id={source_url_id} date={stat_date}"
            )
        return row


def _try_consume_quota_sync(
    conn: pymysql.connections.Connection, stat_date: date, daily_quota: int
) -> tuple[bool, int, str]:
    """事务内原子扣配额。"""
    quota = max(0, int(daily_quota))
    with conn.cursor() as cur:
        row = _ensure_row_locked_sync(
            conn,
            guard_scope=GUARD_SCOPE_GLOBAL,
            source_url_id=0,
            stat_date=stat_date,
        )
        used = int(row.get("agent_used") or 0)
        if used >= quota:
            conn.commit()
            return False, used, f"Agent 兜底已达当日配额（{used}/{quota}）"

        new_used = used + 1
        cur.execute(
            f"""
            UPDATE radar_news_agent_guard
            SET agent_used = %s, version = version + 1, update_time = NOW()
            WHERE id = %s AND {_NOT_DELETED}
            """,
            (new_used, int(row["id"])),
        )
        conn.commit()
        return True, new_used, ""


def _is_system_tripped_sync(stat_date: date) -> bool:
    """只读：全局是否熔断。"""
    from backend.infrastructure.database.mysql_connection import query_one

    row = query_one(
        f"""
        SELECT system_tripped FROM radar_news_agent_guard
        WHERE guard_scope = %s AND source_url_id = 0 AND stat_date = %s
          AND {_NOT_DELETED}
        """,
        (GUARD_SCOPE_GLOBAL, stat_date),
    )
    return bool(row and int(row.get("system_tripped") or 0) == 1)


def _is_source_skipped_sync(source_url_id: int, stat_date: date) -> bool:
    """只读：该源是否跳过。"""
    from backend.infrastructure.database.mysql_connection import query_one

    if int(source_url_id) <= 0:
        return False
    row = query_one(
        f"""
        SELECT content_skipped FROM radar_news_agent_guard
        WHERE guard_scope = %s AND source_url_id = %s AND stat_date = %s
          AND {_NOT_DELETED}
        """,
        (GUARD_SCOPE_SOURCE, int(source_url_id), stat_date),
    )
    return bool(row and int(row.get("content_skipped") or 0) == 1)


def _mark_system_result_sync(
    conn: pymysql.connections.Connection,
    stat_date: date,
    *,
    success: bool,
    max_streak: int,
) -> bool:
    """事务内更新系统 streak / tripped。"""
    threshold = max(1, int(max_streak))
    with conn.cursor() as cur:
        row = _ensure_row_locked_sync(
            conn,
            guard_scope=GUARD_SCOPE_GLOBAL,
            source_url_id=0,
            stat_date=stat_date,
        )
        if success:
            streak = 0
            tripped = 0
        else:
            streak = int(row.get("system_fail_streak") or 0) + 1
            tripped = 1 if streak >= threshold else int(row.get("system_tripped") or 0)
            if tripped and not int(row.get("system_tripped") or 0):
                logger.warning(
                    "Agent 兜底系统熔断：连续系统失败 %d 次，当日不再兜底", streak
                )

        cur.execute(
            f"""
            UPDATE radar_news_agent_guard
            SET system_fail_streak = %s, system_tripped = %s,
                version = version + 1, update_time = NOW()
            WHERE id = %s AND {_NOT_DELETED}
            """,
            (streak, tripped, int(row["id"])),
        )
        conn.commit()
        return bool(tripped)


def _mark_content_result_sync(
    conn: pymysql.connections.Connection,
    source_url_id: int,
    stat_date: date,
    *,
    success: bool,
    increment_streak: bool,
    max_streak: int,
) -> bool:
    """事务内更新该源 content streak / skipped。"""
    sid = int(source_url_id)
    if sid <= 0:
        conn.commit()
        return False

    threshold = max(1, int(max_streak))
    with conn.cursor() as cur:
        row = _ensure_row_locked_sync(
            conn,
            guard_scope=GUARD_SCOPE_SOURCE,
            source_url_id=sid,
            stat_date=stat_date,
        )
        if success:
            streak = 0
            skipped = 0
        elif not increment_streak:
            # 临时故障：不推 skip，保持原 streak
            conn.commit()
            return bool(int(row.get("content_skipped") or 0))
        else:
            streak = int(row.get("content_fail_streak") or 0) + 1
            skipped = 1 if streak >= threshold else int(row.get("content_skipped") or 0)
            if skipped and not int(row.get("content_skipped") or 0):
                logger.warning(
                    "Agent 兜底按源跳过：source_url_id=%s 连续内容失败 %d 次",
                    sid,
                    streak,
                )

        cur.execute(
            f"""
            UPDATE radar_news_agent_guard
            SET content_fail_streak = %s, content_skipped = %s,
                version = version + 1, update_time = NOW()
            WHERE id = %s AND {_NOT_DELETED}
            """,
            (streak, skipped, int(row["id"])),
        )
        conn.commit()
        return bool(skipped)


class MysqlAgentGuardStore:
    """exhibition MySQL 上的闸门存储。"""

    async def is_system_tripped(self, stat_date: date) -> bool:
        """当日全局是否已系统熔断。"""
        return await run_db(_is_system_tripped_sync, stat_date)

    async def is_source_skipped(self, source_url_id: int, stat_date: date) -> bool:
        """该信息源当日是否已跳过 Agent。"""
        return await run_db(_is_source_skipped_sync, int(source_url_id), stat_date)

    async def try_consume_quota(
        self, stat_date: date, daily_quota: int
    ) -> tuple[bool, int, str]:
        """原子扣减日配额。"""
        return await run_db(
            run_in_transaction,
            _try_consume_quota_sync,
            stat_date,
            daily_quota,
        )

    async def mark_system_result(
        self, stat_date: date, *, success: bool, max_streak: int
    ) -> bool:
        """记录系统侧结果。"""
        return await run_db(
            run_in_transaction,
            _mark_system_result_sync,
            stat_date,
            success=success,
            max_streak=max_streak,
        )

    async def mark_content_result(
        self,
        source_url_id: int,
        stat_date: date,
        *,
        success: bool,
        increment_streak: bool,
        max_streak: int,
    ) -> bool:
        """记录该信息源内容侧结果。"""
        return await run_db(
            run_in_transaction,
            _mark_content_result_sync,
            int(source_url_id),
            stat_date,
            success=success,
            increment_streak=increment_streak,
            max_streak=max_streak,
        )


# ================================================================ 内存（单测）

@dataclass
class _MemGlobal:
    """内存 GLOBAL 行。"""

    agent_used: int = 0
    system_fail_streak: int = 0
    system_tripped: bool = False


@dataclass
class _MemSource:
    """内存 SOURCE 行。"""

    content_fail_streak: int = 0
    content_skipped: bool = False


@dataclass
class InMemoryAgentGuardStore:
    """
        进程内闸门存储（语义对齐 MySQL 版，供单测）。

        用线程锁保护，便于并发扣配额用例。
    """

    _lock: threading.Lock = field(default_factory=threading.Lock)
    _global: dict[date, _MemGlobal] = field(default_factory=dict)
    _sources: dict[tuple[date, int], _MemSource] = field(default_factory=dict)

    def _global_row(self, stat_date: date) -> _MemGlobal:
        """取或建 GLOBAL 行。"""
        if stat_date not in self._global:
            self._global[stat_date] = _MemGlobal()
        return self._global[stat_date]

    def _source_row(self, stat_date: date, source_url_id: int) -> _MemSource:
        """取或建 SOURCE 行。"""
        key = (stat_date, int(source_url_id))
        if key not in self._sources:
            self._sources[key] = _MemSource()
        return self._sources[key]

    async def is_system_tripped(self, stat_date: date) -> bool:
        """当日全局是否已系统熔断。"""
        with self._lock:
            return self._global_row(stat_date).system_tripped

    async def is_source_skipped(self, source_url_id: int, stat_date: date) -> bool:
        """该信息源当日是否已跳过 Agent。"""
        if int(source_url_id) <= 0:
            return False
        with self._lock:
            return self._source_row(stat_date, int(source_url_id)).content_skipped

    async def try_consume_quota(
        self, stat_date: date, daily_quota: int
    ) -> tuple[bool, int, str]:
        """原子扣减日配额。"""
        quota = max(0, int(daily_quota))
        with self._lock:
            row = self._global_row(stat_date)
            if row.agent_used >= quota:
                return (
                    False,
                    row.agent_used,
                    f"Agent 兜底已达当日配额（{row.agent_used}/{quota}）",
                )
            row.agent_used += 1
            return True, row.agent_used, ""

    async def mark_system_result(
        self, stat_date: date, *, success: bool, max_streak: int
    ) -> bool:
        """记录系统侧结果。"""
        threshold = max(1, int(max_streak))
        with self._lock:
            row = self._global_row(stat_date)
            if success:
                row.system_fail_streak = 0
            else:
                row.system_fail_streak += 1
                if row.system_fail_streak >= threshold:
                    row.system_tripped = True
            return row.system_tripped

    async def mark_content_result(
        self,
        source_url_id: int,
        stat_date: date,
        *,
        success: bool,
        increment_streak: bool,
        max_streak: int,
    ) -> bool:
        """记录该信息源内容侧结果。"""
        sid = int(source_url_id)
        if sid <= 0:
            return False
        threshold = max(1, int(max_streak))
        with self._lock:
            row = self._source_row(stat_date, sid)
            if success:
                row.content_fail_streak = 0
                row.content_skipped = False
            elif increment_streak:
                row.content_fail_streak += 1
                if row.content_fail_streak >= threshold:
                    row.content_skipped = True
            return row.content_skipped


__all__ = [
    "AgentGuardStore",
    "GUARD_SCOPE_GLOBAL",
    "GUARD_SCOPE_SOURCE",
    "InMemoryAgentGuardStore",
    "MysqlAgentGuardStore",
    "today_stat_date",
]
