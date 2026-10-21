"""
规则二 v3 请求组装（M2）。

目标架构：Java 只产任务，Python 自行读取任务与历史事件，组装模型请求体。
设计：华院Agent设计/02-技术设计/03-Worker调度与数据模型.md §5。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date
from typing import Any, Optional

import pymysql

from backend.app.api.schemas.huayuan_radar_event import DEFAULT_QUERY_HINT

log = logging.getLogger("radar_score.prepare")

# 历史事件摘要上限（避免 prompt 过长）
MAX_HISTORY_EVENTS = 20


def _bit_bool(value: Any) -> bool:
    """MySQL bit/bool → Python bool（b'\\x00'→False，b'\\x01'→True）。"""
    if isinstance(value, (bytes, bytearray)):
        return any(value)
    if isinstance(value, str):
        return value not in ("", "\x00", "0", "false", "False")
    return bool(value)


def fetch_job_and_company(
    conn: pymysql.Connection, job_id: int, *, tenant_id: Optional[int] = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
        读取任务与所属企业。

        Args:
            conn: 数据库连接
            job_id: 任务编号
            tenant_id: 租户过滤（None 不过滤）

        Returns:
            (job, company)

        Raises:
            ValueError: 任务或企业不存在
    """
    tenant_sql = " AND tenant_id = %s" if tenant_id is not None else ""
    tenant_params = [tenant_id] if tenant_id is not None else []
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT * FROM radar_event_job WHERE id = %s AND deleted = b'0'{tenant_sql}",
            [job_id, *tenant_params],
        )
        job = cur.fetchone()
    if not job:
        raise ValueError(f"radar_event_job 不存在: id={job_id}")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM radar_company WHERE id = %s AND deleted = b'0'",
            [job["company_id"]],
        )
        company = cur.fetchone()
    if not company:
        raise ValueError(f"radar_company 不存在: id={job['company_id']}")
    return job, company


# 单次从库预取的原始行上限（分组后会显著变少，故放大）
_HISTORY_SCAN_LIMIT = 200


def _row_to_history(r: dict[str, Any]) -> dict[str, Any]:
    """radar_event 行 → history 摘要 dict。"""
    return {
        "id": r.get("id"),
        "event_name": r.get("event_name"),
        "parent_event_id": r.get("parent_event_id"),
        "space_object": r.get("space_object"),
        "place": r.get("place"),
        "procurement_scope": r.get("procurement_scope"),
        "event_stage": r.get("event_stage"),
        "exhibition_stage": r.get("exhibition_stage"),
        "system_level": r.get("system_level"),
        "verify_status": r.get("verify_status"),
        "validity_status": r.get("validity_status"),
        "expired_or_done": _bit_bool(r.get("expired_or_done")),
        "published": _bit_bool(r.get("published")),
        "total_score": r.get("total_score"),
        "signal_summary": r.get("signal_summary"),
        "rule_version": r.get("rule_version"),
        "update_time": str(r.get("update_time")) if r.get("update_time") else None,
    }


def _is_closed_row(row: dict[str, Any]) -> bool:
    """该事件是否已失效/关闭（事件自身层）。"""
    if row.get("expired_or_done"):
        return True
    return str(row.get("validity_status") or "").strip().upper() in {"EXPIRED", "INVALID"}


def _group_latest_by_root(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
        按「商机族」聚组、每组取最新一条作代表；**族内状态取"或"**。

        族键 = `parent_event_id or id`（约定子事件直接指向根，单层）。
        `published` / `closed` 必须按族取或——**已发布那条往往不是最新**。

        Args:
            rows: 已解析的 history 行

        Returns:
            每组一条代表行（含 `root_event_id` / `published` / `closed` / `member_count` / `member_ids`），按更新时间倒序
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        root_key = str(row.get("parent_event_id") or row.get("id"))
        groups.setdefault(root_key, []).append(row)

    out: list[dict[str, Any]] = []
    for root_key, members in groups.items():
        members_sorted = sorted(
            members,
            key=lambda x: (str(x.get("update_time") or ""), int(x.get("id") or 0)),
            reverse=True,
        )
        rep = dict(members_sorted[0])
        rep["root_event_id"] = int(root_key)
        rep["published"] = any(m.get("published") for m in members)
        rep["closed"] = any(_is_closed_row(m) for m in members)
        rep["member_count"] = len(members)
        rep["member_ids"] = [int(m.get("id")) for m in members]
        out.append(rep)
    out.sort(
        key=lambda x: (str(x.get("update_time") or ""), int(x.get("id") or 0)),
        reverse=True,
    )
    return out


def _attach_opportunity_status(
    conn: pymysql.Connection,
    groups: list[dict[str, Any]],
    *,
    tenant_id: Optional[int] = None,
) -> None:
    """
        批量补商机状态（`radar_opportunity.status`），就地写回每组的 `opportunity_status`。

        商机只挂在"被发布的那条事件"上，故按**族内全部事件 id** 查，命中即取（避免 N+1）。

        Args:
            conn: 数据库连接
            groups: `_group_latest_by_root` 产物（就地修改）
            tenant_id: 租户过滤
    """
    all_ids = [eid for g in groups for eid in (g.get("member_ids") or [])]
    if not all_ids:
        return
    tenant_sql = " AND tenant_id = %s" if tenant_id is not None else ""
    tenant_params = [tenant_id] if tenant_id is not None else []
    placeholders = ", ".join(["%s"] * len(all_ids))
    sql = (
        "SELECT source_event_id, status, close_reason, closed_at "
        "FROM radar_opportunity "
        f"WHERE deleted = b'0'{tenant_sql} AND source_event_id IN ({placeholders})"
    )
    with conn.cursor() as cur:
        cur.execute(sql, [*tenant_params, *all_ids])
        rows = list(cur.fetchall() or [])
    by_event: dict[int, dict[str, Any]] = {
        int(r["source_event_id"]): r for r in rows if r.get("source_event_id") is not None
    }
    for g in groups:
        hit: Optional[dict[str, Any]] = None
        for eid in g.get("member_ids") or []:
            if eid in by_event:
                hit = by_event[eid]
                break
        g["opportunity_status"] = (
            (str(hit.get("status") or "").strip() or None) if hit else None
        )
        g["opportunity_close_reason"] = (hit.get("close_reason") or None) if hit else None


def load_history_events(
    conn: pymysql.Connection,
    company_id: int,
    *,
    tenant_id: Optional[int] = None,
    limit: int = MAX_HISTORY_EVENTS,
) -> list[dict[str, Any]]:
    """
        读取该企业既有事件摘要（供 Agent 判断"同一商机"）。

        261020：**按商机族去重、每组只给最新一条**，并补商机状态 —— 给模型的数据更少、指认更简单。
        - 族键 = `parent_event_id or id`；
        - `published` / `closed` 取族内"或"（已发布那条往往不是最新）；
        - 附 `opportunity_status`（`radar_opportunity.status`，只读）。

        Args:
            conn: 数据库连接
            company_id: 企业编号
            tenant_id: 租户过滤
            limit: 返回的商机组数上限

        Returns:
            每组一条的摘要列表（按更新时间倒序）
    """
    tenant_sql = " AND tenant_id = %s" if tenant_id is not None else ""
    tenant_params = [tenant_id] if tenant_id is not None else []
    sql = f"""
        SELECT id, event_name, parent_event_id, space_object, place, procurement_scope, event_stage, exhibition_stage,
               system_level, verify_status, validity_status, expired_or_done, published,
               total_score, signal_summary, rule_version, update_time
        FROM radar_event
        WHERE company_id = %s AND deleted = b'0'{tenant_sql}
        ORDER BY update_time DESC
        LIMIT %s
    """
    scan_limit = max(int(limit) * 5, _HISTORY_SCAN_LIMIT)
    with conn.cursor() as cur:
        cur.execute(sql, [company_id, *tenant_params, int(scan_limit)])
        rows = list(cur.fetchall() or [])

    groups = _group_latest_by_root([_row_to_history(r) for r in rows])
    _attach_opportunity_status(conn, groups, tenant_id=tenant_id)
    return groups[: int(limit)]


def build_history_json(history: list[dict[str, Any]]) -> str:
    """历史事件摘要序列化为 prompt 占位符字符串。"""
    return json.dumps(history, ensure_ascii=False, default=str)


def _company_context(company: dict[str, Any]) -> dict[str, Any]:
    """radar_company 行 → 请求 context.company。"""
    name = str(company.get("name") or "").strip()
    raw_stock_name = str(company.get("stock_name_raw") or "").strip()
    aliases: list[str] = []
    if raw_stock_name and raw_stock_name != name:
        aliases.append(raw_stock_name)
    return {
        "company_id": company.get("id"),
        "company_name": name,
        "stock_code": company.get("stock_code"),
        "aliases": aliases,
        "industry": company.get("industry"),
        "region": company.get("region"),
    }


def _date_str(value: Any) -> Optional[str]:
    """date/datetime/str → YYYY-MM-DD。"""
    if value is None:
        return None
    if isinstance(value, (date,)):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    return text[:10] if text else None


def build_request_body(
    job: dict[str, Any],
    company: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    """
        组装与手动路径一致的模型请求体。

        Args:
            job: radar_event_job 行
            company: radar_company 行
            history: 历史事件摘要
            trace_id: 可选 Trace ID

        Returns:
            HuayuanRadarEventRequest 形状的 dict
    """
    tid = trace_id or uuid.uuid4().hex
    company_ctx = _company_context(company)
    return {
        "query": f"评估「{company_ctx['company_name']}」的展厅需求证据强度并给出评分与证据。",
        "trace_id": tid,
        "context": {
            "company": company_ctx,
            "time_from": _date_str(job.get("time_from")),
            "time_to": _date_str(job.get("time_to")),
            "query_hint": DEFAULT_QUERY_HINT,
            "event_job_id": job.get("id"),
            "history_events_json": build_history_json(history),
        },
    }