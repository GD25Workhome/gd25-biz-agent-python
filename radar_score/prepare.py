"""
规则二 v3 请求组装（M2）。

目标架构：Java 只产任务，Python 自行读取任务与历史事件，组装模型请求体。
设计：华院Agent设计/261016-Agent重构/Agent整体设计/05-详细设计.md §3。
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


def load_history_events(
    conn: pymysql.Connection,
    company_id: int,
    *,
    tenant_id: Optional[int] = None,
    limit: int = MAX_HISTORY_EVENTS,
) -> list[dict[str, Any]]:
    """
        读取该企业既有事件摘要（供 Agent 判断同一事件新阶段 / 独立新需求）。

        Args:
            conn: 数据库连接
            company_id: 企业编号
            tenant_id: 租户过滤
            limit: 上限

        Returns:
            摘要列表（按更新时间倒序）
    """
    tenant_sql = " AND tenant_id = %s" if tenant_id is not None else ""
    tenant_params = [tenant_id] if tenant_id is not None else []
    sql = f"""
        SELECT id, space_object, place, procurement_scope, event_stage, exhibition_stage,
               system_level, verify_status, validity_status, expired_or_done, total_score,
               signal_summary, update_time
        FROM radar_event
        WHERE company_id = %s AND deleted = b'0'{tenant_sql}
        ORDER BY update_time DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, [company_id, *tenant_params, int(limit)])
        rows = list(cur.fetchall() or [])
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.get("id"),
                "space_object": r.get("space_object"),
                "place": r.get("place"),
                "procurement_scope": r.get("procurement_scope"),
                "event_stage": r.get("event_stage"),
                "exhibition_stage": r.get("exhibition_stage"),
                "system_level": r.get("system_level"),
                "verify_status": r.get("verify_status"),
                "validity_status": r.get("validity_status"),
                "expired_or_done": _bit_bool(r.get("expired_or_done")),
                "total_score": r.get("total_score"),
                "signal_summary": r.get("signal_summary"),
                "update_time": str(r.get("update_time")) if r.get("update_time") else None,
            }
        )
    return out


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