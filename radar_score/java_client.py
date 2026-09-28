"""
回调 Java：取 context、提交模型原始结果。

画像：
  POST {base}/admin-api/radar/profile-job/score-prepare
  POST {base}/admin-api/radar/profile-job/score-complete
展厅需求：
  POST {base}/admin-api/radar/event-job/score-prepare
  POST {base}/admin-api/radar/event-job/score-complete

请求头 X-Radar-Score-Token 携带 RADAR_SCORE_JAVA_TOKEN。
prepare 成功时 data.requestBody 与现有 Agent HTTP body 相同。
complete 体：jobId、lockedBy、ok、agentResp、errorMessage。
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional

from radar_score.config import ScoreSettings
from radar_score.repository import table_of

log = logging.getLogger("radar_score.java_client")

TOKEN_HEADER = "X-Radar-Score-Token"
_UNAVAILABLE_HTTP = {404, 502, 503, 504}

_PREPARE_PATH = {
    "profile": "/admin-api/radar/profile-job/score-prepare",
    "event": "/admin-api/radar/event-job/score-prepare",
}
_COMPLETE_PATH = {
    "profile": "/admin-api/radar/profile-job/score-complete",
    "event": "/admin-api/radar/event-job/score-complete",
}


class JavaScoreError(RuntimeError):
    """Java 返回了业务错误。"""


class JavaUnavailable(RuntimeError):
    """Java 不可达，或内部接口尚未部署。"""


def assert_java_ok(payload: Any) -> None:
    """
        只校验芋道 CommonResult 的 code。

        complete 成功时 data 是 true，不是对象。

        Args:
            payload: HTTP JSON

        Raises:
            JavaScoreError: 响应不是对象，或 code 非成功
    """
    if not isinstance(payload, dict):
        raise JavaScoreError("Java 响应不是 JSON 对象")
    if "code" not in payload:
        return
    code = payload.get("code")
    if code not in (0, 200, "0", "200"):
        raise JavaScoreError(str(payload.get("msg") or f"code={code}"))


def unwrap_java_data(payload: Any) -> dict[str, Any]:
    """
        解开芋道 CommonResult；没有 code 字段时把对象本身当作 data。

        Args:
            payload: HTTP JSON

        Returns:
            data 对象

        Raises:
            JavaScoreError: code 非成功或 data 不是对象
    """
    if not isinstance(payload, dict):
        raise JavaScoreError("Java 响应不是 JSON 对象")
    if "code" in payload and "data" in payload:
        assert_java_ok(payload)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise JavaScoreError("Java data 不是对象")
        return data
    return payload


def extract_request_body(data: dict[str, Any]) -> dict[str, Any]:
    """
        从 prepare 的 data 中取出发给模型的 body。

        Args:
            data: unwrap 后的 data

        Returns:
            requestBody

        Raises:
            JavaScoreError: 缺少 requestBody
    """
    body = data.get("requestBody")
    if body is None:
        body = data.get("request_body")
    if not isinstance(body, dict):
        raise JavaScoreError("prepare 未返回 requestBody")
    return body


def _url(settings: ScoreSettings, kind: str, paths: dict[str, str]) -> str:
    # table_of：拒绝未知 kind，避免拼出任意路径
    table_of(kind)
    return settings.java_base_url + paths[kind]


def _post_json(settings: ScoreSettings, url: str, body: dict[str, Any]) -> dict[str, Any]:
    """
        POST JSON 并解析响应。

        Args:
            settings: 调度配置
            url: 完整地址
            body: 请求体

        Returns:
            响应 JSON 对象

        Raises:
            JavaUnavailable: 网络错误或 404/502/503/504
            JavaScoreError: 其它 HTTP 错误或空响应
    """
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=raw, method="POST")
    request.add_header("Content-Type", "application/json; charset=utf-8")
    if settings.java_token:
        request.add_header(TOKEN_HEADER, settings.java_token)
    try:
        with urllib.request.urlopen(request, timeout=settings.java_timeout_sec) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as ex:
        detail = ex.read().decode("utf-8", errors="replace")[:300]
        if ex.code in _UNAVAILABLE_HTTP:
            raise JavaUnavailable(f"HTTP {ex.code} {url} {detail}") from ex
        raise JavaScoreError(f"HTTP {ex.code} {url} {detail}") from ex
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        raise JavaUnavailable(f"{url} {ex}") from ex
    if not text.strip():
        raise JavaScoreError(f"Java 响应为空 {url}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as ex:
        raise JavaScoreError(f"Java 响应不是 JSON {url}") from ex
    if not isinstance(parsed, dict):
        raise JavaScoreError(f"Java 响应不是对象 {url}")
    return parsed


def prepare(settings: ScoreSettings, kind: str, job_id: int) -> dict[str, Any]:
    """
        向 Java 索取与手动路径相同的模型请求体。

        Args:
            settings: 调度配置
            kind: profile 或 event
            job_id: 已认领的任务编号

        Returns:
            requestBody
    """
    url = _url(settings, kind, _PREPARE_PATH)
    payload = _post_json(
        settings,
        url,
        {"jobId": int(job_id), "lockedBy": settings.locked_by},
    )
    return extract_request_body(unwrap_java_data(payload))


def complete(
    settings: ScoreSettings,
    kind: str,
    job_id: int,
    *,
    ok: bool,
    agent_resp: Optional[dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> None:
    """
        把模型原始 JSON 或失败原因交回 Java 落库。

        Args:
            settings: 调度配置
            kind: profile 或 event
            job_id: 任务编号
            ok: 模型调用是否成功
            agent_resp: 成功时的原始响应
            error_message: 失败原因
    """
    url = _url(settings, kind, _COMPLETE_PATH)
    message = (error_message or "")[:900] or None
    payload = _post_json(
        settings,
        url,
        {
            "jobId": int(job_id),
            "lockedBy": settings.locked_by,
            "ok": bool(ok),
            "agentResp": agent_resp,
            "errorMessage": message,
        },
    )
    assert_java_ok(payload)
    log.info("complete kind=%s jobId=%s ok=%s", kind, job_id, ok)
