"""
规则二 v3 直写落库（M7）。

目标架构：Python 端到端落库——写 radar_event / radar_event_evidence，更新 radar_event_job。
约束：所有写函数**不 commit**（由调用方事务提交/回滚），便于单测回滚与失败整体回滚。
设计：华院Agent设计/02-技术设计/02-评分、自检与落库规则.md §5。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

import pymysql

from backend.app.api.schemas.huayuan_radar_event import RadarEventScoreResult
from radar_score.self_check import SelfCheckOutcome

log = logging.getLogger("radar_score.radar_event_store")

RULE_VERSION_V3 = "v3-2026-10-14"

STATUS_SUCCESS = 2
STATUS_FAILED = 3

_ACTOR = "python-score"


def _bit(value: Any) -> int:
    """布尔 → bit 列取值 0/1。"""
    return 1 if value else 0


def _json(value: Any, *, maxlen: Optional[int] = None) -> Optional[str]:
    """序列化为 JSON 字符串；超长截断。"""
    if value is None:
        return None
    text = json.dumps(value, ensure_ascii=False, default=str)
    if maxlen and len(text) > maxlen:
        text = text[:maxlen]
    return text


def _normalize_priority(value: Optional[str]) -> Optional[str]:
    """P0–P3 规范化（非法 → None）。"""
    s = str(value or "").strip().upper()
    return s if s in {"P0", "P1", "P2", "P3"} else None


# varchar 列宽（与 exhibition DDL 一致；超长会 1406 整单回滚，与 Java RadarScoreFieldTruncate 同口径）
# 261020：按实测「大胆加宽」——见 exhibition SQL脚本/48_、/49_（幂等，已应用）
_EVENT_MAX = {
    "space_object": 512,
    "event_name": 255,
    "action": 255,
    "place": 255,
    "time_text": 128,
    "signal_summary": 512,
    "signal_time": 32,
    "signal_category": 255,
    "verify_priority_reason": 1000,
    "admission_reason": 1000,
    "score_reason": 4000,
    "suggested_level_reason": 1000,
    "rule_version": 64,
    "subject_confidence": 32,
    "fact_status": 32,
    "admission_hint": 64,
    "target_scope": 32,
    "procurement_scope": 64,
    "event_stage": 64,
    "exhibition_stage": 64,
    "date_precision": 32,
    "validity_status": 32,
    "verify_status": 64,
    "region_name": 255,
    "region_path_ids": 512,
    "region_source": 64,
}

_EVIDENCE_MAX = {
    "title": 1024,
    "summary": 4000,
    "quote": 4000,
    "cite_reason": 2000,
    "source_url": 2048,
    "source_host": 255,
    "authority_tier": 64,
    "source_type": 64,
    "source_level": 16,
    "publish_date": 64,
}


def _clip(value: Any, maxlen: int) -> Any:
    """
        按列宽截断字符串，避免 MySQL 1406「Data too long」导致整单回滚。

        Args:
            value: 原始值（None / 非字符串原样返回）
            maxlen: 列宽

        Returns:
            截断后的值
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    return value if len(value) <= maxlen else value[:maxlen]


def _clip_optional_text(value: Any, maxlen: int) -> Optional[str]:
    """可选文本：去空白、空串 → None，再按列宽截断。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if len(text) <= maxlen else text[:maxlen]


def _resolve_level_verify_admission(
    score: RadarEventScoreResult, outcome: SelfCheckOutcome
) -> dict[str, Any]:
    """
        由评分 + 自检结果推导准入/等级/核验状态。

        Returns:
            {admission_pass, admission_reason, system_level, final_level,
             validity_status, verify_status}
    """
    excluded = (not score.exhibition_related) or score.expired_or_done
    if excluded:
        validity = "EXPIRED" if score.expired_or_done else "INVALID"
        reason = score.score_reason or ("需求已失效或已完成" if score.expired_or_done else "与展厅需求无关或不准入")
        return {
            "admission_pass": 0,
            "admission_reason": reason,
            "system_level": None,
            "final_level": None,
            "validity_status": validity,
            "verify_status": "CANDIDATE",
        }

    level = outcome.level_final
    hint = (score.admission_hint or "").strip().lower()
    fact = (score.fact_status or "unknown").strip().lower()
    pending = (
        hint == "pending_verify"
        or (score.subject_confidence or "unknown").strip().lower() == "unknown"
        or fact in {"unknown", "conflict"}
    )
    high_level = level in {"S1", "S2"}
    verify_status = "PENDING_VERIFY" if (pending or high_level) else "CANDIDATE"
    return {
        "admission_pass": 1,
        "admission_reason": "准入通过",
        "system_level": level,
        "final_level": level,
        "validity_status": "ACTIVE",
        "verify_status": verify_status,
    }


def touch_latest_event(conn: pymysql.Connection, company_id: Any, event_id: Any) -> int:
    """
        把企业「最新展厅事件」指针指向本次事件。

        对齐 Java `RadarCompanyMapper#updateLatestEventId` / `repairLatestEventIds`
        （`radar_company.latest_event_id = MAX(id)`）；客户雷达列表按该指针 JOIN 事件，
        指针不更新会导致企业关联不到新事件（列表/详情显示旧事件或无信号）。

        只前移不回退：指针已指向更新的（或已发布被 Java 挂在雷达上的）事件时保持不动。

        Args:
            conn: 连接（不 commit）
            company_id: 企业编号
            event_id: 本次写入的事件编号

        Returns:
            受影响行数（0 表示未前移）
    """
    if not company_id or not event_id:
        return 0
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE radar_company SET latest_event_id = %s "
            "WHERE id = %s AND deleted = b'0' "
            "AND (latest_event_id IS NULL OR latest_event_id < %s)",
            [int(event_id), int(company_id), int(event_id)],
        )
        return int(cur.rowcount or 0)


def fetch_region_source(conn: pymysql.Connection, event_id: int) -> Optional[str]:
    """
        读取既有事件的区域来源，用于保护人工修正（MANUAL）不被重算覆盖。

        Args:
            conn: 连接
            event_id: 事件 id

        Returns:
            region_source；事件不存在或列为空时 None
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT region_source FROM radar_event WHERE id = %s AND deleted = b'0'",
            [int(event_id)],
        )
        row = cur.fetchone()
    return (row or {}).get("region_source")


def _event_columns(
    job: dict[str, Any],
    score: RadarEventScoreResult,
    outcome: SelfCheckOutcome,
    trace_id: str,
    region: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
        评分结果 → radar_event 列字典。

        Args:
            job: radar_event_job 行
            score: 评分结果
            outcome: 自检结果
            trace_id: Trace ID
            region: 展厅所在区域列（region_resolve.resolve_event_region 产物）；
                None 表示本次不写区域列（保留既有值，如人工修正）

        Returns:
            列名 → 值
    """
    derived = _resolve_level_verify_admission(score, outcome)
    cols = {
        "company_id": job["company_id"],
        "event_job_id": job["id"],
        "space_object": score.space_object,
        "event_name": score.event_name,
        "parent_event_id": score.parent_event_id,
        "action": score.action,
        "place": score.place,
        "time_text": score.time_text,
        "signal_summary": score.signal_summary,
        "signal_time": score.signal_time,
        "signal_time_evidence_no": score.signal_time_evidence_no,
        "event_tags_json": _json(score.tags, maxlen=2000),
        "exhibition_related": _bit(score.exhibition_related),
        "subject_confidence": score.subject_confidence,
        "admission_hint": score.admission_hint,
        "admission_pass": derived["admission_pass"],
        "admission_reason": derived["admission_reason"],
        "evidence_score": score.evidence_score,
        "specificity_score": score.specificity_score,
        "total_score": score.total_score,
        "score_reason": score.score_reason,
        "score_items_json": _json([it.model_dump() for it in score.score_items]),
        "system_level": derived["system_level"],
        "final_level": derived["final_level"],
        "validity_status": derived["validity_status"],
        "verify_status": derived["verify_status"],
        "fact_status": score.fact_status,
        "expired_or_done": _bit(score.expired_or_done),
        "published": 0,
        # v3 扩展列
        "target_scope": score.target_scope,
        "suggested_level": score.suggested_level,
        "suggested_level_reason": score.suggested_level_reason,
        "procurement_scope": score.procurement_scope,
        "event_stage": score.event_stage,
        "exhibition_stage": score.exhibition_stage,
        "is_potential": _bit(score.is_potential),
        "signal_category": score.signal_category,
        "verify_priority_default": _normalize_priority(score.verify_priority_default),
        "verify_priority_adjusted": _normalize_priority(score.verify_priority_adjusted),
        "verify_priority_reason": score.verify_priority_reason,
        "planned_time": score.planned_time,
        "expected_time": score.expected_time,
        "actual_time": score.actual_time,
        "date_precision": score.date_precision,
        # 元信息
        "rule_version": score.rule_version or RULE_VERSION_V3,
        "agent_trace_id": trace_id,
        "updater": _ACTOR,
    }
    # 展厅所在区域（place 解析 / 继承企业）；None 时不写，保留既有值
    if region is not None:
        cols.update(region)
    # 按 varchar 列宽截断，避免 1406 整单回滚（signal_summary 空串归一为 NULL）
    cols["signal_summary"] = _clip_optional_text(cols.get("signal_summary"), _EVENT_MAX["signal_summary"])
    for key, limit in _EVENT_MAX.items():
        if key in cols:
            cols[key] = _clip(cols[key], limit)
    return cols


def insert_event(
    conn: pymysql.Connection,
    job: dict[str, Any],
    score: RadarEventScoreResult,
    outcome: SelfCheckOutcome,
    trace_id: str,
    region: Optional[dict[str, Any]] = None,
) -> int:
    """
        新建雷达事件。

        Args:
            conn: 连接（不 commit）
            job: radar_event_job 行
            score: 评分结果
            outcome: 自检结果
            trace_id: Trace ID
            region: 展厅所在区域列（缺省不写）

        Returns:
            新事件 id
    """
    cols = _event_columns(job, score, outcome, trace_id, region)
    cols["tenant_id"] = int(job.get("tenant_id") or 0)
    cols["creator"] = _ACTOR
    cols["create_time"] = datetime.now()
    cols["update_time"] = datetime.now()
    names = ", ".join(f"`{k}`" for k in cols)
    placeholders = ", ".join(["%s"] * len(cols))
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO radar_event ({names}) VALUES ({placeholders})",
            list(cols.values()),
        )
        event_id = int(cur.lastrowid)
    return event_id


def update_event(
    conn: pymysql.Connection,
    event_id: int,
    job: dict[str, Any],
    score: RadarEventScoreResult,
    outcome: SelfCheckOutcome,
    trace_id: str,
    region: Optional[dict[str, Any]] = None,
) -> None:
    """
        推进/覆盖既有事件（同事件新阶段）。

        ⚠️ **261019 起停用**：事件决策改为「只插、不更、不关」，此函数不再被调用
        （且会覆盖 `published` / `verify_status`）。保留仅为将来「子事件」落地时参考。

        Args:
            conn: 连接（不 commit）
            event_id: 既有事件 id
            job: 当前任务行
            score: 本次评分
            outcome: 自检结果
            trace_id: Trace ID
            region: 展厅所在区域列；None 时保留既有区域（如人工 MANUAL）
    """
    cols = _event_columns(job, score, outcome, trace_id, region)
    cols["event_job_id"] = job["id"]
    cols["update_time"] = datetime.now()
    assignments = ", ".join(f"`{k}` = %s" for k in cols)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE radar_event SET {assignments} WHERE id = %s AND deleted = b'0'",
            [*cols.values(), int(event_id)],
        )


def replace_evidences(
    conn: pymysql.Connection,
    event_id: int,
    score: RadarEventScoreResult,
    *,
    tenant_id: int = 0,
) -> int:
    """
        以 kept 证据重建该事件的证据行（先删后插，保持幂等）。

        - `evidence_no`：**事件内序号**（按 kept 顺序 `0..n-1`），与 `score_items.evidence_nos` /
          `signal_time_evidence_no` 对齐（261020 补）。
        - `cite_reason`：引用原因（261020 补，此前 v3 路径漏写）。

        Args:
            conn: 连接（不 commit）
            event_id: 事件 id
            score: 评分结果
            tenant_id: 租户

        Returns:
            写入条数
    """
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM radar_event_evidence WHERE event_id = %s AND deleted = b'0'",
            [int(event_id)],
        )
    rows: list[list[Any]] = []
    now = datetime.now()
    evidence_no = 0
    for ev in score.evidences:
        if not ev.kept:
            continue
        rows.append(
            [
                event_id,
                evidence_no,
                _clip(ev.title, _EVIDENCE_MAX["title"]),
                _clip(ev.summary, _EVIDENCE_MAX["summary"]),
                _clip(ev.quote, _EVIDENCE_MAX["quote"]),
                _clip(ev.cite_reason, _EVIDENCE_MAX["cite_reason"]),
                _clip(ev.url, _EVIDENCE_MAX["source_url"]),
                _clip(ev.publish_date, _EVIDENCE_MAX["publish_date"]),
                _clip(ev.source_host, _EVIDENCE_MAX["source_host"]),
                _clip(ev.authority_tier, _EVIDENCE_MAX["authority_tier"]),
                _bit(True),
                _clip(str(ev.source_type or "web"), _EVIDENCE_MAX["source_type"]),
                _clip(str(ev.source_level or "P2").upper(), _EVIDENCE_MAX["source_level"]),
                _ACTOR,
                now,
                _ACTOR,
                now,
                tenant_id,
            ]
        )
        evidence_no += 1
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO radar_event_evidence
                (event_id, evidence_no, title, summary, quote, cite_reason, source_url,
                 publish_date, source_host, authority_tier, kept, source_type, source_level,
                 creator, create_time, updater, update_time, tenant_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            rows,
        )
    return len(rows)


def update_job_success(
    conn: pymysql.Connection,
    job_id: int,
    *,
    event_id: Optional[int],
    trace_id: str,
    acp_raw_json: Optional[str],
    stats_json: Optional[str],
    cost_ms: int,
    revision_json: Optional[str] = None,
) -> None:
    """
        任务成功收口（status=2，回写 event_id/stats；event_id 可为 None=NOOP）。

        Args:
            revision_json: 复核留痕（裁定 D12）——`rule_gate` 的 before/after/判定 +
                `auditor` 的 audit 说明；写入 `radar_event_job.revision_json`（mediumtext）
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE radar_event_job
            SET status = %s, event_id = %s, agent_trace_id = %s, acp_raw_json = %s,
                stats_json = %s, revision_json = %s, cost_ms = %s, error_message = NULL,
                locked_by = NULL, locked_at = NULL, updater = %s, update_time = %s
            WHERE id = %s AND deleted = b'0'
            """,
            [
                STATUS_SUCCESS,
                int(event_id) if event_id is not None else None,
                trace_id,
                acp_raw_json,
                (stats_json or "")[:60000] or None,
                revision_json,
                int(cost_ms),
                _ACTOR,
                datetime.now(),
                int(job_id),
            ],
        )


def update_job_failed(conn: pymysql.Connection, job_id: int, message: str) -> None:
    """任务失败收口（status=3）。"""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE radar_event_job
            SET status = %s, error_message = %s, locked_by = NULL, locked_at = NULL,
                updater = %s, update_time = %s
            WHERE id = %s AND deleted = b'0'
            """,
            [STATUS_FAILED, (message or "")[:900], _ACTOR, datetime.now(), int(job_id)],
        )