"""领到任务后的一次执行：prepare → 进程内算分 → complete。"""
from __future__ import annotations

import logging
from typing import Any

from radar_score.config import EVENT_KIND, PROFILE_KIND, ScoreSettings
from radar_score.java_client import JavaScoreError, JavaUnavailable, complete, prepare
from radar_score.repository import connect, release_claim

log = logging.getLogger("radar_score.execute")


async def _score(kind: str, request_body: dict[str, Any]) -> dict[str, Any]:
    """
        调用现有评分接口函数，返回与 HTTP 响应相同的 JSON。

        Args:
            kind: profile 或 event
            request_body: Java prepare 给出的 body

        Returns:
            模型原始响应

        Raises:
            ValueError: 未知类型
    """
    if kind == PROFILE_KIND:
        from backend.app.api.routes.huayuan_portrait import huayuan_portrait
        from backend.app.api.schemas.huayuan_portrait import HuayuanPortraitRequest

        # huayuan_portrait：进程内走现有五维流程，不经 HTTP
        request = HuayuanPortraitRequest.model_validate(request_body)
        response = await huayuan_portrait(request)
        return response.model_dump(mode="json")
    if kind == EVENT_KIND:
        from backend.app.api.routes.huayuan_radar_event import huayuan_radar_event_score
        from backend.app.api.schemas.huayuan_radar_event import HuayuanRadarEventRequest

        # huayuan_radar_event_score：进程内走现有展厅需求流程
        request = HuayuanRadarEventRequest.model_validate(request_body)
        response = await huayuan_radar_event_score(request)
        return response.model_dump(mode="json")
    raise ValueError(f"未知评分任务类型: {kind}")


def _release(settings: ScoreSettings, kind: str, job_id: int, reason: str) -> None:
    conn = connect(settings)
    try:
        release_claim(conn, settings, kind, job_id, reason)
    finally:
        conn.close()


async def execute_claimed_job(settings: ScoreSettings, kind: str, job_id: int) -> None:
    """
        执行一条已认领任务。

        Java 不可达且模型还没调用时，退回 PENDING。
        模型已经跑完但落库回调失败时，保持 RUNNING，等超时回收，避免立刻重算。

        Args:
            settings: 调度配置
            kind: profile 或 event
            job_id: 任务编号

        Raises:
            JavaUnavailable: prepare 阶段 Java 不可达（调用方据此退避）
    """
    # 1. 取与手动路径相同的 context
    try:
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
        通知 Java 把任务写成失败。

        Args:
            settings: 调度配置
            kind: profile 或 event
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
