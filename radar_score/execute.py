"""
规则二 event 任务的一次执行（event-only）。

- event：端到端——直连库读任务/历史 → 进程内算分 → 自检 → 直写落库 → 任务收口。
- profile / 画像已下线，不再支持。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import pymysql

from backend.app.api.schemas.huayuan_radar_event import RadarEventScoreResult
from radar_score import event_update, region_resolve
from radar_score import radar_event_store as store
from radar_score.self_check import check
from radar_score.config import EVENT_KIND, ScoreSettings
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

        可重试：网络/依赖抖动（OperationalError、模型网关超时等）。
        不可重试：数据或结构类确定性错误，重跑只会再失败 → 直接标记 FAILED，避免任务反复重跑。

        ⚠️ 会**沿异常链**（`__cause__` / `__context__`）判断：路由把 `ValueError` 包成
        `HTTPException` 后，外层类型看不出确定性，必须看内层原因（否则会反复重试）。

        Args:
            ex: 捕获到的异常

        Returns:
            True 表示可退回 PENDING 重试
    """
    cur: BaseException = ex
    for _ in range(8):  # 有界遍历，防异常链成环
        if isinstance(cur, _NON_RETRYABLE):
            return False
        nxt = cur.__cause__ or cur.__context__
        if nxt is None or nxt is cur:
            break
        cur = nxt
    return True


async def _score(request_body: dict[str, Any]) -> dict[str, Any]:
    """
        调用规则二评分接口函数，返回与 HTTP 响应相同的 JSON。

        Args:
            request_body: 模型请求体

        Returns:
            模型原始响应
    """
    from backend.app.api.routes.huayuan_radar_event import huayuan_radar_event_score
    from backend.app.api.schemas.huayuan_radar_event import HuayuanRadarEventRequest

    request = HuayuanRadarEventRequest.model_validate(request_body)
    response = await huayuan_radar_event_score(request)
    return response.model_dump(mode="json")


def _release(
    settings: ScoreSettings, job_id: int, reason: str, *, retryable: bool = True
) -> None:
    conn = connect(settings)
    try:
        release_claim(conn, settings, EVENT_KIND, job_id, reason, retryable=retryable)
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

        # 算分（进程内调 route；不含最终落库）——v3 支持一次多个事件
        resp = await _score(body)
        raw_scores = resp.get("radar_event_scores") or []
        if not raw_scores:
            raw_scores = [resp.get("radar_event_score") or {}]
        scores = [RadarEventScoreResult.model_validate(s or {}) for s in raw_scores]
        if not scores:
            raise ValueError("算分结果为空：radar_event_scores / radar_event_score 均缺失")

        tenant_id = int(job.get("tenant_id") or 0)
        events_stats: list[dict[str, Any]] = []
        passed = 0
        written_event_id: Optional[int] = None

        # 逐个事件：自检 → 决策（只插/不落库）→ 落库
        for score in scores:
            outcome = check(score)
            if not outcome.ok:
                # 单个事件自检不通过 → 跳过该条（不落脏数据），不整体失败
                events_stats.append(
                    {
                        "action": "SELF_CHECK_FAILED",
                        "notes": outcome.notes,
                        "event_name": score.event_name,
                    }
                )
                continue
            passed += 1
            decision = event_update.decide_action(score, history)
            # 展厅所在区域：Agent 字典结果 → place 解析 → 继承企业
            region = region_resolve.resolve_event_region(
                conn, score.place, company, place_region_id=score.place_region_id
            )
            event_id: Optional[int] = None
            if decision.action == event_update.INSERT:
                # 同一商机的时间线：代码算出的族根优先于模型自报的 parent
                if decision.parent_event_id is not None:
                    score.parent_event_id = decision.parent_event_id
                event_id = store.insert_event(conn, job, score, outcome, trace_id, region)
                store.replace_evidences(conn, event_id, score, tenant_id=tenant_id)
                # 企业↔事件关联：指针前移到新事件，客户雷达才能关联到它
                store.touch_latest_event(conn, job["company_id"], event_id)
            else:  # NOOP：不落库（已发布/已关闭/已完成）
                event_id = decision.event_id
            if event_id:
                written_event_id = event_id
            events_stats.append(
                {
                    "action": decision.action,
                    "event_id": event_id,
                    "parent_event_id": score.parent_event_id if decision.action == event_update.INSERT else None,
                    "reason": decision.reason,
                    "event_ref": score.event_ref,
                    "event_name": score.event_name,
                    "event_relation": score.event_relation,
                    "level_final": outcome.level_final,
                }
            )

        if passed == 0:
            store.update_job_failed(
                conn, job_id, "全部事件自检未通过：" + json.dumps(events_stats, ensure_ascii=False)[:800]
            )
            conn.commit()
            log.warning("全部事件自检未通过 jobId=%s", job_id)
            return

        cost_ms = int((time.monotonic() - started) * 1000)
        stats = json.dumps(
            {"events": events_stats, "event_count": len(scores)},
            ensure_ascii=False,
        )
        store.update_job_success(
            conn,
            job_id,
            event_id=written_event_id,
            trace_id=trace_id,
            acp_raw_json=json.dumps(resp, ensure_ascii=False),
            stats_json=stats,
            cost_ms=cost_ms,
            revision_json=(
                json.dumps(resp.get("revision"), ensure_ascii=False, default=str)
                if resp.get("revision")
                else None
            ),
        )
        conn.commit()
        log.info(
            "event 端到端完成 jobId=%s events=%s costMs=%s stats=%s",
            job_id,
            len(scores),
            cost_ms,
            stats,
        )
    except Exception as ex:
        conn.rollback()
        log.exception("event 端到端失败 jobId=%s", job_id)
        # 确定性错误（数据/结构）→ 标记 FAILED；网络/依赖抖动 → 退回 PENDING 重试
        _release(
            settings,
            job_id,
            f"{type(ex).__name__}: {ex}",
            retryable=is_retryable(ex),
        )
        raise
    finally:
        conn.close()


async def execute_claimed_job(settings: ScoreSettings, kind: str, job_id: int) -> None:
    """
        执行一条已认领任务（只支持 event）。

        Args:
            settings: 调度配置
            kind: 任务类型；只允许 event
            job_id: 任务编号

        Raises:
            ValueError: 非 event 类型
    """
    if kind != EVENT_KIND:
        raise ValueError(f"未知评分任务类型: {kind}")
    await run_event_end_to_end(settings, job_id)
