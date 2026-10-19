"""
领到任务后的一次执行。

- event（规则二 v3）：**端到端**——直连库读任务/历史 → 进程内算分 → 自检 → 直写落库 → 任务收口。
- profile（五维画像）：沿用 Java prepare/complete 握手（本版暂不动）。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import pymysql

from backend.app.api.schemas.huayuan_radar_event import RadarEventScoreResult
from radar_score import event_update, region_resolve
from radar_score import radar_event_store as store
from radar_score.self_check import check
from radar_score.config import EVENT_KIND, PROFILE_KIND, ScoreSettings
from radar_score.java_client import JavaScoreError, JavaUnavailable, complete, prepare
from radar_score.repository import connect, release_claim

log = logging.getLogger("radar_score.execute")

# 确定性错误：数据/结构不合规（如列超长 1406、值不合法 1366、类型错误），重跑必然再失败
_NON_RETRYABLE = (
    pymysql.err.DataError,
    pymysql.err.IntegrityError,
    pymysql.err.ProgrammingError,
    pymysql.err.NotSupportedError,
    ValueError,
    TypeError,
    KeyError,
)


def is_retryable(ex: BaseException) -> bool:
    """
        判断异常是否值得重试。

        可重试：网络/依赖抖动（JavaUnavailable、OperationalError、模型网关超时等）。
        不可重试：数据或结构类确定性错误，重跑只会再失败 → 直接标记 FAILED，避免任务反复重跑。

        Args:
            ex: 捕获到的异常

        Returns:
            True 表示可退回 PENDING 重试
    """
    return not isinstance(ex, _NON_RETRYABLE)


async def _score(kind: str, request_body: dict[str, Any]) -> dict[str, Any]:
    """
        调用现有评分接口函数，返回与 HTTP 响应相同的 JSON。

        Args:
            kind: profile 或 event
            request_body: 模型请求体

        Returns:
            模型原始响应

        Raises:
            ValueError: 未知类型
    """
    if kind == PROFILE_KIND:
        from backend.app.api.routes.huayuan_portrait import huayuan_portrait
        from backend.app.api.schemas.huayuan_portrait import HuayuanPortraitRequest

        request = HuayuanPortraitRequest.model_validate(request_body)
        response = await huayuan_portrait(request)
        return response.model_dump(mode="json")
    if kind == EVENT_KIND:
        from backend.app.api.routes.huayuan_radar_event import huayuan_radar_event_score
        from backend.app.api.schemas.huayuan_radar_event import HuayuanRadarEventRequest

        request = HuayuanRadarEventRequest.model_validate(request_body)
        response = await huayuan_radar_event_score(request)
        return response.model_dump(mode="json")
    raise ValueError(f"未知评分任务类型: {kind}")


def _release(
    settings: ScoreSettings, kind: str, job_id: int, reason: str, *, retryable: bool = True
) -> None:
    conn = connect(settings)
    try:
        release_claim(conn, settings, kind, job_id, reason, retryable=retryable)
    finally:
        conn.close()


async def run_event_end_to_end(settings: ScoreSettings, job_id: int) -> None:
    """
        规则二 v3 端到端执行（单任务一事务）。

        流程：读任务/企业/历史 → 组装 → 算分 → 自检 → 直写落库 → 任务 SUCCESS。
        异常：回滚 + 退回 PENDING（可重试）；自检不通过：任务 FAILED（不落脏数据）。

        Args:
            settings: 调度配置
            job_id: 已认领的任务编号
    """
    from radar_score import prepare  # 延迟导入，避免循环依赖

    conn = connect(settings)
    started = time.monotonic()
    try:
        job, company = prepare.fetch_job_and_company(
            conn, job_id, tenant_id=settings.tenant_id
        )
        history = prepare.load_history_events(
            conn, job["company_id"], tenant_id=settings.tenant_id
        )
        body = prepare.build_request_body(job, company, history)
        trace_id = str(body.get("trace_id") or "")

        # 算分（进程内调 route；不含最终落库）
        resp = await _score(EVENT_KIND, body)
        score = RadarEventScoreResult.model_validate(resp.get("radar_event_score") or {})

        # 自检：不通过 → FAILED（不落脏数据）
        outcome = check(score)
        if not outcome.ok:
            store.update_job_failed(conn, job_id, "; ".join(outcome.notes) or "自检未通过")
            conn.commit()
            log.warning("自检未通过 jobId=%s notes=%s", job_id, outcome.notes)
            return

        # 直写落库：事件更新决策（M6）—— INSERT / UPDATE / NOOP
        decision = event_update.decide_action(score, history)
        tenant_id = int(job.get("tenant_id") or 0)
        # 展厅所在区域：Agent 字典结果 → place 解析 → 继承企业；人工 MANUAL 不被重算覆盖
        region = region_resolve.resolve_event_region(
            conn, score.place, company, place_region_id=score.place_region_id
        )
        if (
            decision.action == event_update.UPDATE
            and decision.event_id is not None
            and store.fetch_region_source(conn, decision.event_id) == region_resolve.SOURCE_MANUAL
        ):
            region = None
        event_id: Optional[int] = None
        if decision.action == event_update.INSERT:
            event_id = store.insert_event(conn, job, score, outcome, trace_id, region)
            store.replace_evidences(conn, event_id, score, tenant_id=tenant_id)
            # 企业↔事件关联：指针前移到新事件，客户雷达才能关联到它
            store.touch_latest_event(conn, job["company_id"], event_id)
        elif decision.action == event_update.UPDATE and decision.event_id is not None:
            event_id = decision.event_id
            store.update_event(conn, event_id, job, score, outcome, trace_id, region)
            store.replace_evidences(conn, event_id, score, tenant_id=tenant_id)
            store.touch_latest_event(conn, job["company_id"], event_id)
        else:  # NOOP：不写事件（可能仍指向既有事件）
            event_id = decision.event_id

        cost_ms = int((time.monotonic() - started) * 1000)
        stats = json.dumps(
            {
                "self_check": {
                    "level_final": outcome.level_final,
                    "cap_reason": outcome.cap_reason,
                    "notes": outcome.notes,
                },
                "event_update": {
                    "action": decision.action,
                    "event_id": decision.event_id,
                    "reason": decision.reason,
                },
            },
            ensure_ascii=False,
        )
        store.update_job_success(
            conn,
            job_id,
            event_id=event_id,
            trace_id=trace_id,
            acp_raw_json=json.dumps(resp, ensure_ascii=False),
            stats_json=stats,
            cost_ms=cost_ms,
        )
        conn.commit()
        log.info(
            "event 端到端完成 jobId=%s action=%s eventId=%s level=%s costMs=%s",
            job_id,
            decision.action,
            event_id,
            outcome.level_final,
            cost_ms,
        )
    except Exception as ex:
        conn.rollback()
        log.exception("event 端到端失败 jobId=%s", job_id)
        # 确定性错误（数据/结构）→ 标记 FAILED；网络/依赖抖动 → 退回 PENDING 重试
        _release(
            settings,
            EVENT_KIND,
            job_id,
            f"{type(ex).__name__}: {ex}",
            retryable=is_retryable(ex),
        )
        raise
    finally:
        conn.close()


async def execute_claimed_job(settings: ScoreSettings, kind: str, job_id: int) -> None:
    """
        执行一条已认领任务。

        event 走 Python 端到端；profile 沿用 Java prepare/complete 握手。

        Args:
            settings: 调度配置
            kind: profile 或 event
            job_id: 任务编号
    """
    if kind == EVENT_KIND:
        await run_event_end_to_end(settings, job_id)
        return

    # ---------------- profile：沿用 Java 握手（本版不动） ----------------
    try:
        # 1. 取与手动路径相同的 context
        request_body = prepare(settings, kind, job_id)
    except JavaUnavailable as ex:
        _release(settings, kind, job_id, f"Java 不可用，退回待执行: {ex}")
        raise
    except Exception as ex:
        log.exception("prepare 失败 kind=%s jobId=%s", kind, job_id)
        _try_complete_failure(settings, kind, job_id, ex)
        return

    # 2. 进程内算分
    try:
        agent_resp = await _score(kind, request_body)
    except Exception as ex:
        log.exception("算分失败 kind=%s jobId=%s", kind, job_id)
        _try_complete_failure(settings, kind, job_id, ex)
        return

    # 3. 交回 Java 校验、定级、落库
    try:
        complete(settings, kind, job_id, ok=True, agent_resp=agent_resp)
    except Exception:
        log.exception(
            "评分已完成但 complete 失败，保持 RUNNING 等超时回收 kind=%s jobId=%s",
            kind,
            job_id,
        )


def _try_complete_failure(
    settings: ScoreSettings,
    kind: str,
    job_id: int,
    ex: BaseException,
) -> None:
    """
        通知 Java 把任务写成失败（仅 profile 路径使用）。

        Args:
            settings: 调度配置
            kind: 任务类型
            job_id: 任务编号
            ex: 失败原因
    """
    message = f"{type(ex).__name__}: {ex}"
    try:
        complete(settings, kind, job_id, ok=False, error_message=message)
    except JavaUnavailable as down:
        log.warning(
            "complete 不可达，保持 RUNNING kind=%s jobId=%s err=%s",
            kind,
            job_id,
            down,
        )
    except JavaScoreError:
        log.exception("complete 业务失败 kind=%s jobId=%s", kind, job_id)