"""AnySearch 纯传输客户端：search / extract + key failover + error_code。

设计：`05-AnySearch-统一工具封装设计.md` §9（沿用 260924-01 契约）。
- 不含华院依赖；结果归一化与 enrichment 由调用方（华院薄适配层）负责。
- 传输可通过 `post_fn` 注入（单测用，不打外网）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.domain.tools.anysearch import store
from backend.domain.tools.anysearch.errors import (
    ANYSEARCH_BAD_REQUEST,
    ANYSEARCH_KEYS_EXHAUSTED,
    ANYSEARCH_RATE_LIMITED,
    ANYSEARCH_TIMEOUT,
    ANYSEARCH_UPSTREAM_ERROR,
)
from backend.domain.tools.anysearch.pool import (
    HEALTH_COOLING,
    HEALTH_EXHAUSTED,
    HEALTH_INVALID,
    AnySearchPool,
    KeyRef,
    get_anysearch_pool,
)
from backend.domain.tools.anysearch.rate import TokenBucket

logger = logging.getLogger(__name__)

_BASE = "https://api.anysearch.com"
_TIMEOUT_SEC = 30.0
# 401/402/403：凭证问题（带 request_id 的 403 才算）
_REJECT_STATUS = frozenset({401, 402, 403})
# 请求或 URL 不合法：不熔断、不换 key
_BAD_REQUEST_STATUS = frozenset({400, 415, 422})

# post_fn 契约：(url, headers, payload) -> (status|None, body|None)
PostFn = Any


@dataclass
class Outcome:
    """一次 failover 调用的结果。"""

    ok: bool
    body: Any = None
    error: str = ""
    error_code: str = ""
    http_status: Optional[int] = None

    def to_payload(self, **extra: Any) -> str:
        """收成工具/调用方用的 JSON 字符串。"""
        data: Dict[str, Any] = {"ok": False, "error": self.error, "error_code": self.error_code}
        if self.http_status is not None:
            data["http_status"] = self.http_status
        data.update(extra)
        return json.dumps(data, ensure_ascii=False)


def _request_id(status: int, headers: Any, body: Any) -> str:
    """
        取 request_id（不返回、不记录响应正文；402 体可能含对方密钥）。

        Args:
            status: HTTP 状态
            headers: 响应头
            body: 已解析 JSON

        Returns:
            request_id；无则空串
    """
    try:
        header = (headers.get("X-Request-ID") or "").strip() if headers else ""
    except Exception:  # noqa: BLE001
        header = ""
    if header:
        return header
    if isinstance(body, dict):
        rid = body.get("request_id")
        if isinstance(rid, str):
            return rid.strip()
    return ""


def _business_ok(body: Any) -> bool:
    """2xx 后看业务 code：缺 code 或 code==0 视为成功。"""
    if not isinstance(body, dict) or "code" not in body:
        return True
    return body.get("code") == 0


class AnySearchClient:
    """AnySearch HTTP 客户端（带 key failover）。"""

    def __init__(
        self,
        pool: Optional[AnySearchPool] = None,
        *,
        timeout_sec: float = _TIMEOUT_SEC,
        post_fn: Optional[PostFn] = None,
    ) -> None:
        """
            Args:
                pool: 凭证池；缺省用进程单例
                timeout_sec: HTTP 超时
                post_fn: 注入的自定义传输（单测用）；None 走 httpx
        """
        self._pool = pool or get_anysearch_pool()
        self._timeout = float(timeout_sec)
        self._post_fn = post_fn

        # 供应商限速（DeepSeek：Search 100 / Fetch 25，取 80% 作为阈值）：
        # 达到阈值即由令牌桶排队降速，工具内部兜底不触碰供应商上限。
        # 注入 post_fn（单测 mock 传输）时不启用，避免拖慢测试。
        self._provider_buckets: Dict[str, TokenBucket] = {}
        if post_fn is None:
            try:
                cfg = self._pool.get_config()
                self._provider_buckets["/v1/search"] = TokenBucket(
                    cfg.provider_search_qps, max(1.0, min(cfg.provider_search_qps, 10.0))
                )
                self._provider_buckets["/v1/extract"] = TokenBucket(
                    cfg.provider_fetch_qps, max(1.0, min(cfg.provider_fetch_qps, 10.0))
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("AnySearch 供应商限速桶初始化失败（忽略）: %s", exc)

    async def _acquire_provider(self, path: str) -> None:
        """按操作类型取供应商限速令牌（search / extract 分别限速）。"""
        bucket = self._provider_buckets.get(path)
        if bucket is not None:
            await bucket.acquire()

    # ------------------------------------------------------------ 外部接口
    async def search(self, query: str, max_results: int = 0) -> Dict[str, Any]:
        """
            联网检索。

            Args:
                query: 检索式
                max_results: 返回条数上限（0 表示用默认 5）

            Returns:
                {"ok": True, "query", "results", "result_count"} 或失败结构
        """
        limit = int(max_results) if max_results and int(max_results) > 0 else 5
        limit = max(1, min(10, limit))
        payload = {"query": str(query or "").strip(), "max_results": limit, "zone": "cn", "language": "zh-CN"}
        outcome = await self._post_with_key_failover("/v1/search", payload)
        if not outcome.ok:
            return json.loads(outcome.to_payload(query=payload["query"]))
        results = _normalize_search_items(outcome.body)
        return {
            "ok": True,
            "query": payload["query"],
            "results": results,
            "result_count": len(results),
            "tool_name": "anysearch_web_search",
        }

    async def extract(self, url: str) -> Dict[str, Any]:
        """
            抽取指定 URL 正文（Markdown）。

            Args:
                url: 目标 http(s) URL

            Returns:
                {"ok": True, "url", "content", "truncated"} 或失败结构
        """
        target = str(url or "").strip()
        outcome = await self._post_with_key_failover("/v1/extract", {"url": target})
        if not outcome.ok:
            return json.loads(outcome.to_payload(url=target))
        content = _extract_content(outcome.body)
        return {"ok": True, "url": target, "content": content, "truncated": False}

    # ------------------------------------------------------------ failover
    async def _post_with_key_failover(self, path: str, payload: Dict[str, Any]) -> Outcome:
        """
            用池里的 key 依次重放同一请求体。

            - 取不到 key / 换完仍全被拒 → keys_exhausted
            - 401 / 402 / 带 request_id 的 403 → 熔断该 key，换下一把
            - 429 → 冷却 + 降速，返回 rate_limited（不再换 key）
            - 400/415/422、无 request_id 的 403 → bad_request（不熔断）
            - 5xx / 业务码失败 → upstream_error
            - 超时 → timeout

            Args:
                path: 以 /v1/ 开头的路径
                payload: JSON 请求体

            Returns:
                Outcome
        """
        cfg = self._pool.get_config()
        max_tries = max(1, int(cfg.max_failover_keys))
        url = f"{_BASE}{path}"
        tried: set[int] = set()

        for _ in range(max_tries):
            key = await self._pool.acquire()
            if key is None or key.id in tried:
                return Outcome(ok=False, error="AnySearch 凭证不可用", error_code=ANYSEARCH_KEYS_EXHAUSTED)
            tried.add(key.id)

            # 供应商限速：每次真实请求前取令牌（达 80% 阈值即排队降速）
            await self._acquire_provider(path)
            status, body, err = await self._post_once(url, key, payload)
            if err == "timeout":
                self._pool.mark_result(key, ok=False, error_code=ANYSEARCH_TIMEOUT, reason="请求超时")
                return Outcome(ok=False, error="AnySearch 请求超时", error_code=ANYSEARCH_TIMEOUT)

            if status is None:
                self._pool.mark_result(key, ok=False, error_code=ANYSEARCH_UPSTREAM_ERROR, reason="网络失败")
                return Outcome(ok=False, error="AnySearch 网络失败", error_code=ANYSEARCH_UPSTREAM_ERROR)

            # 403 无 request_id：单条请求异常，不熔断
            if status == 403 and not _request_id(status, None, body):
                return Outcome(ok=False, error="AnySearch 请求被拒绝", error_code=ANYSEARCH_BAD_REQUEST, http_status=403)

            if status in _REJECT_STATUS:
                health = HEALTH_EXHAUSTED if status == 402 else HEALTH_INVALID
                self._pool.mark_result(
                    key, ok=False, health=health, error_code=ANYSEARCH_KEYS_EXHAUSTED,
                    reason=f"凭证被拒 HTTP {status}",
                )
                continue  # 换下一把

            if status == 429:
                self._pool.on_rate_limited(key.id)
                self._pool.mark_result(
                    key, ok=False, health=HEALTH_COOLING, error_code=ANYSEARCH_RATE_LIMITED,
                    reason="限流", cooldown_ms=cfg.cooldown_429_ms,
                )
                return Outcome(ok=False, error="AnySearch 限流", error_code=ANYSEARCH_RATE_LIMITED, http_status=429)

            if status in _BAD_REQUEST_STATUS:
                return Outcome(ok=False, error="AnySearch 请求无效", error_code=ANYSEARCH_BAD_REQUEST, http_status=status)

            if status < 200 or status >= 300:
                self._pool.mark_result(key, ok=False, error_code=ANYSEARCH_UPSTREAM_ERROR, reason=f"上游 {status}")
                return Outcome(ok=False, error="AnySearch 上游失败", error_code=ANYSEARCH_UPSTREAM_ERROR, http_status=status)

            if not _business_ok(body):
                return Outcome(ok=False, error="AnySearch 业务失败", error_code=ANYSEARCH_UPSTREAM_ERROR, http_status=status)

            self._pool.mark_result(key, ok=True)
            return Outcome(ok=True, body=body, http_status=status)

        return Outcome(ok=False, error="AnySearch 凭证不可用", error_code=ANYSEARCH_KEYS_EXHAUSTED)

    async def _post_once(self, url: str, key: KeyRef, payload: Dict[str, Any]) -> Tuple[Optional[int], Any, str]:
        """
            单次 POST（注入传输优先）。

            Returns:
                (status|None, body|None, err)；err=="timeout" 表示超时
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {key.value}",
        }
        if self._post_fn is not None:
            status, body = await self._post_fn(url, headers, payload)
            return status, body, ""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException:
            return None, None, "timeout"
        except httpx.HTTPError:
            return None, None, ""
        rid = resp.headers.get("X-Request-ID")
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            body = None
        if rid and isinstance(body, dict):
            body.setdefault("request_id", rid)
        return resp.status_code, body, ""


def _normalize_search_items(raw: Any) -> List[Dict[str, Any]]:
    """把 AnySearch 响应归一为结果列表（保留 url/title/snippet/content）。"""
    if raw is None:
        return []
    data = raw
    if isinstance(raw, dict):
        if isinstance(raw.get("data"), dict):
            data = raw["data"]
        elif isinstance(raw.get("data"), list):
            return [x for x in raw["data"] if isinstance(x, dict)]
        elif isinstance(raw.get("results"), list):
            return [x for x in raw["results"] if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in ("results", "items", "documents", "data"):
            val = data.get(k)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
    return []


def _extract_content(body: Any) -> str:
    """从抽取响应里取正文（markdown/text/body 兜底）。"""
    if isinstance(body, dict):
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        if isinstance(data, dict):
            return str(data.get("content") or data.get("markdown") or data.get("text") or data.get("body") or "")
        if isinstance(body.get("data"), str):
            return body["data"]
    if isinstance(body, str):
        return body
    return ""


__all__ = ["AnySearchClient", "Outcome"]