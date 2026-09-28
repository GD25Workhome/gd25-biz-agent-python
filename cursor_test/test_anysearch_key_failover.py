"""
AnySearch 凭证池故障转移单测。

HTTP 全部 mock，不访问 api.anysearch.com。
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx
import pytest

pytest_plugins = ("pytest_asyncio",)
pytestmark = pytest.mark.asyncio

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.app.config import settings
from backend.domain.tools import anysearch_tool
from backend.domain.tools.anysearch_tool import (
    get_anysearch_key_pool,
    has_live_key,
    resolve_anysearch_keys,
)
from backend.domain.tools.huayuan_radar_event_context import (
    HuayuanRadarEventContext,
    build_radar_event_context_from_request,
)

_KEY_A = "test-anysearch-key-aaaa1111"
_KEY_B = "test-anysearch-key-bbbb2222"


class _FakeResponse:
    """只提供 status_code / headers / json，供 failover 分类。"""

    def __init__(
        self,
        status_code: int,
        body: Any,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def json(self) -> Any:
        """返回预设 JSON。body 为 Exception 时模拟解析失败。"""
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class _ScriptedClient:
    """按脚本依次返回响应或抛异常，并记下每次请求头。"""

    def __init__(self, script: List[Union[_FakeResponse, Exception]]) -> None:
        self._script = list(script)
        self.calls: List[Dict[str, Any]] = []

    async def __aenter__(self) -> "_ScriptedClient":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    async def post(self, url: str, headers: Optional[Dict[str, str]] = None, json: Any = None) -> _FakeResponse:
        """弹出下一条脚本。脚本耗尽说明换 key 次数超出预期。"""
        self.calls.append({"url": url, "headers": dict(headers or {}), "json": json})
        if not self._script:
            raise AssertionError("HTTP 调用次数超过脚本")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _reset_pool() -> Any:
    """每个用例前后清空熔断集，避免串到本机 .env 里的真实 key。"""
    get_anysearch_key_pool().reset()
    yield
    get_anysearch_key_pool().reset()


def _use_keys(*keys: str) -> None:
    """注入测试凭证池，不再读取 Settings。"""
    get_anysearch_key_pool().configure(list(keys))


def _patch_http(monkeypatch: pytest.MonkeyPatch, script: List[Union[_FakeResponse, Exception]]) -> _ScriptedClient:
    """替换 AsyncClient，使工具走脚本响应。"""
    client = _ScriptedClient(script)
    monkeypatch.setattr(anysearch_tool.httpx, "AsyncClient", lambda *args, **kwargs: client)
    return client


def _context() -> HuayuanRadarEventContext:
    """构造允许搜索和抽取的请求级上下文。"""
    data = build_radar_event_context_from_request(
        company_name="鼎捷数智",
        stock_code="300378",
        aliases=[],
        max_bocha=0,
        max_anysearch=5,
        max_extract_times=3,
        max_results_per_search=3,
        max_extract_chars=1000,
        event_job_id=None,
        trace_id="test-anysearch-failover",
    )
    return HuayuanRadarEventContext(data)


def _auth(call: Dict[str, Any]) -> str:
    """取出这次请求的 Authorization。"""
    return str(call["headers"].get("Authorization") or "")


def _ok_search(results: Optional[List[Dict[str, Any]]] = None) -> _FakeResponse:
    """构造 code=0 的搜索成功响应。"""
    return _FakeResponse(
        200,
        {"code": 0, "message": "success", "data": {"results": results or []}},
    )


@pytest.mark.parametrize(
    ("status", "query"),
    [(402, "额度用完换key"), (401, "无效key换下一把"), (403, "过期key换下一把")],
)
async def test_reject_status_switches_to_next_key(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    query: str,
) -> None:
    """401 / 402 / 403 熔断第一把，并用第二把重放同一请求。"""
    _use_keys(_KEY_A, _KEY_B)
    client = _patch_http(
        monkeypatch,
        [
            _FakeResponse(status, {"code": -1, "message": "rejected", "request_id": "r1"}),
            _ok_search([{"title": "展厅", "url": "https://example.com/a", "snippet": "新建展厅"}]),
        ],
    )
    with _context():
        raw = await anysearch_tool.anysearch_web_search.ainvoke({"query": query, "max_results": 1})
    body = json.loads(raw)
    assert body["ok"] is True
    assert body["result_count"] == 1
    assert body["anysearch_count"] == 1
    assert len(client.calls) == 2
    assert _auth(client.calls[0]) == f"Bearer {_KEY_A}"
    assert _auth(client.calls[1]) == f"Bearer {_KEY_B}"
    assert get_anysearch_key_pool().is_exhausted(_KEY_A)
    assert not get_anysearch_key_pool().is_exhausted(_KEY_B)


async def test_all_keys_rejected_does_not_call_anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    """两把都 402 时返回凭证耗尽，且每次请求都带 Authorization。"""
    _use_keys(_KEY_A, _KEY_B)
    client = _patch_http(
        monkeypatch,
        [
            _FakeResponse(402, {"code": -1, "request_id": "r1"}),
            _FakeResponse(402, {"code": -1, "request_id": "r2"}),
        ],
    )
    with _context():
        raw = await anysearch_tool.anysearch_web_search.ainvoke({"query": "两把都用完", "max_results": 1})
    body = json.loads(raw)
    assert body["ok"] is False
    assert body["error_code"] == "anysearch_keys_exhausted"
    assert body["http_status"] == 402
    assert len(client.calls) == 2
    assert all(_auth(call).startswith("Bearer ") for call in client.calls)
    assert has_live_key() is False


@pytest.mark.parametrize("status", [400, 415, 422])
async def test_bad_request_does_not_exhaust_or_rotate(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    """400 / 415 / 422 是请求或 URL 问题，不熔断，也不打下一把 key。"""
    _use_keys(_KEY_A, _KEY_B)
    client = _patch_http(
        monkeypatch,
        [_FakeResponse(status, {"code": -1, "request_id": "bad-req"})],
    )
    with _context():
        raw = await anysearch_tool.anysearch_web_search.ainvoke(
            {"query": "请求本身无效", "max_results": 1}
        )
    body = json.loads(raw)
    assert body["ok"] is False
    assert body["error_code"] == "anysearch_bad_request"
    assert body["http_status"] == status
    assert len(client.calls) == 1
    assert _auth(client.calls[0]) == f"Bearer {_KEY_A}"
    assert has_live_key() is True
    assert not get_anysearch_key_pool().is_exhausted(_KEY_A)
    assert not get_anysearch_key_pool().is_exhausted(_KEY_B)


async def test_rate_limit_does_not_rotate_or_exhaust(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 不换 key，也不熔断。"""
    _use_keys(_KEY_A, _KEY_B)
    client = _patch_http(monkeypatch, [_FakeResponse(429, {"code": -1, "request_id": "r429"})])
    with _context():
        raw = await anysearch_tool.anysearch_web_search.ainvoke({"query": "被限流", "max_results": 1})
    body = json.loads(raw)
    assert body["error_code"] == "anysearch_rate_limited"
    assert len(client.calls) == 1
    assert not get_anysearch_key_pool().is_exhausted(_KEY_A)
    assert has_live_key() is True


async def test_upstream_tries_next_without_exhaust(monkeypatch: pytest.MonkeyPatch) -> None:
    """502 不熔断，但会改试下一把，避免一次上游失败停住。"""
    _use_keys(_KEY_A, _KEY_B)
    client = _patch_http(
        monkeypatch,
        [
            _FakeResponse(502, {"code": -1}),
            _ok_search([{"title": "展厅", "url": "https://example.com/a", "snippet": "新建展厅"}]),
        ],
    )
    with _context():
        raw = await anysearch_tool.anysearch_web_search.ainvoke({"query": "上游挂了", "max_results": 1})
    body = json.loads(raw)
    assert body["ok"] is True
    assert len(client.calls) == 2
    assert _auth(client.calls[1]) == f"Bearer {_KEY_B}"
    assert not get_anysearch_key_pool().is_exhausted(_KEY_A)
    assert has_live_key() is True


async def test_empty_results_are_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """200 且结果为空是正常没搜到，不打第二把 key。"""
    _use_keys(_KEY_A, _KEY_B)
    client = _patch_http(monkeypatch, [_ok_search([])])
    with _context():
        raw = await anysearch_tool.anysearch_web_search.ainvoke({"query": "空结果", "max_results": 1})
    body = json.loads(raw)
    assert body["ok"] is True
    assert body["result_count"] == 0
    assert len(client.calls) == 1


async def test_timeout_tries_next_key_without_exhaust(monkeypatch: pytest.MonkeyPatch) -> None:
    """超时没有状态码，不熔断，但会改试下一把。"""
    _use_keys(_KEY_A, _KEY_B)
    client = _patch_http(
        monkeypatch,
        [
            httpx.TimeoutException("timed out"),
            _ok_search([{"title": "展厅", "url": "https://example.com/a", "snippet": "新建展厅"}]),
        ],
    )
    with _context():
        raw = await anysearch_tool.anysearch_web_search.ainvoke({"query": "请求超时", "max_results": 1})
    body = json.loads(raw)
    assert body["ok"] is True
    assert len(client.calls) == 2
    assert _auth(client.calls[1]) == f"Bearer {_KEY_B}"
    assert not get_anysearch_key_pool().is_exhausted(_KEY_A)


async def test_all_keys_timeout_returns_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """两把都超时时返回超时，且不把 key 记成当天失效。"""
    _use_keys(_KEY_A, _KEY_B)
    client = _patch_http(
        monkeypatch,
        [httpx.TimeoutException("timed out"), httpx.TimeoutException("timed out")],
    )
    with _context():
        raw = await anysearch_tool.anysearch_web_search.ainvoke({"query": "全部超时", "max_results": 1})
    assert json.loads(raw)["error_code"] == "anysearch_timeout"
    assert len(client.calls) == 2
    assert has_live_key() is True


async def test_business_code_failure_does_not_rotate(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 200 但 code 非 0 时不换 key。"""
    _use_keys(_KEY_A, _KEY_B)
    client = _patch_http(monkeypatch, [_FakeResponse(200, {"code": -1, "message": "busy"})])
    with _context():
        raw = await anysearch_tool.anysearch_web_search.ainvoke({"query": "业务码失败", "max_results": 1})
    assert json.loads(raw)["error_code"] == "anysearch_upstream_error"
    assert len(client.calls) == 1
    assert not get_anysearch_key_pool().is_exhausted(_KEY_A)


async def test_empty_pool_skips_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有 key 时不发请求。"""
    _use_keys()
    client = _patch_http(monkeypatch, [])
    with _context():
        raw = await anysearch_tool.anysearch_web_search.ainvoke({"query": "没有凭证", "max_results": 1})
    body = json.loads(raw)
    assert body["error_code"] == "anysearch_keys_exhausted"
    assert client.calls == []


async def test_extract_422_does_not_exhaust_later_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """抽取 422 只丢掉这一条 URL，后面的 key 保持存活。"""
    _use_keys(_KEY_A, _KEY_B)
    client = _patch_http(
        monkeypatch,
        [_FakeResponse(422, {"code": -1, "request_id": "extract-422"})],
    )
    with _context():
        raw = await anysearch_tool.anysearch_extract.ainvoke({"url": "https://example.com/hall"})
    body = json.loads(raw)
    assert body["ok"] is False
    assert body["error_code"] == "anysearch_bad_request"
    assert body["http_status"] == 422
    assert len(client.calls) == 1
    assert _auth(client.calls[0]) == f"Bearer {_KEY_A}"
    assert has_live_key() is True
    assert not get_anysearch_key_pool().is_exhausted(_KEY_A)
    assert not get_anysearch_key_pool().is_exhausted(_KEY_B)


async def test_extract_switches_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """抽取与搜索共用凭证池。"""
    _use_keys(_KEY_A, _KEY_B)
    client = _patch_http(
        monkeypatch,
        [
            _FakeResponse(403, {"code": -1}),
            _FakeResponse(200, {"code": 0, "data": {"content": "展厅改造招标"}}),
        ],
    )
    with _context():
        raw = await anysearch_tool.anysearch_extract.ainvoke({"url": "https://example.com/hall"})
    body = json.loads(raw)
    assert body["ok"] is True
    assert "展厅改造" in body["content"]
    assert body["extract_count"] == 1
    assert _auth(client.calls[1]) == f"Bearer {_KEY_B}"


async def test_reject_log_omits_secrets(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """402 正文里的 password / api_key 和完整 key 不进日志。"""
    _use_keys(_KEY_A, _KEY_B)
    leaked = {
        "code": -1,
        "message": "password=leak-password-xyz\napi_key=leak-api-key-xyz",
        "request_id": "req-secret-check",
    }
    _patch_http(monkeypatch, [_FakeResponse(402, leaked), _ok_search([])])
    with caplog.at_level(logging.WARNING, logger="backend.domain.tools.anysearch_tool"):
        with _context():
            await anysearch_tool.anysearch_web_search.ainvoke({"query": "日志脱敏", "max_results": 1})
    text = caplog.text
    assert "leak-password-xyz" not in text
    assert "leak-api-key-xyz" not in text
    assert _KEY_A not in text
    assert _KEY_B not in text
    assert "req-secret-check" in text


def test_settings_pool_overrides_single_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """ANY_SEARCH_API_KEYS 非空时忽略单 key。"""
    monkeypatch.setattr(settings, "ANY_SEARCH_API_KEYS", " pool-aaaa1111 , pool-bbbb2222 , pool-aaaa1111 ")
    monkeypatch.setattr(settings, "ANY_SEARCH_API_KEY", "single-should-ignore")
    monkeypatch.setattr(settings, "ANYSEARCH_API_KEY", "official-should-ignore")
    get_anysearch_key_pool().reset()
    assert get_anysearch_key_pool().live_keys() == ["pool-aaaa1111", "pool-bbbb2222"]


def test_single_key_fallback_when_pool_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    """未配多 key 时，按 ANY_SEARCH_API_KEY、ANYSEARCH_API_KEY 组成大小为 1 或 2 的池。"""
    monkeypatch.setattr(settings, "ANY_SEARCH_API_KEYS", "  ")
    monkeypatch.setattr(settings, "ANY_SEARCH_API_KEY", "only-primary-key-zzzz9999")
    monkeypatch.setattr(settings, "ANYSEARCH_API_KEY", None)
    get_anysearch_key_pool().reset()
    assert get_anysearch_key_pool().live_keys() == ["only-primary-key-zzzz9999"]


def test_exhausted_key_retries_on_next_shanghai_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """失效日只挡住当天；上海日历日变为第二天后可再试，再失败则更新日期。"""
    current = {"day": date(2026, 9, 24)}
    monkeypatch.setattr(anysearch_tool, "_quota_today", lambda: current["day"])
    pool = get_anysearch_key_pool()
    pool.configure([_KEY_A, _KEY_B])
    pool.mark_exhausted(_KEY_A)

    assert pool.failure_date(_KEY_A) == date(2026, 9, 24)
    assert pool.is_exhausted(_KEY_A)
    assert pool.live_keys() == [_KEY_B]

    current["day"] = date(2026, 9, 25)
    assert pool.is_exhausted(_KEY_A) is False
    assert pool.live_keys() == [_KEY_A, _KEY_B]

    pool.mark_exhausted(_KEY_A)
    assert pool.failure_date(_KEY_A) == date(2026, 9, 25)
    assert pool.live_keys() == [_KEY_B]


async def test_next_day_search_uses_recovered_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """跨日后搜索会重新打昨天被拒的第一把 key。"""
    current = {"day": date(2026, 9, 24)}
    monkeypatch.setattr(anysearch_tool, "_quota_today", lambda: current["day"])
    _use_keys(_KEY_A, _KEY_B)
    first = _patch_http(
        monkeypatch,
        [
            _FakeResponse(402, {"code": -1, "request_id": "day1"}),
            _ok_search([]),
        ],
    )
    with _context():
        await anysearch_tool.anysearch_web_search.ainvoke({"query": "第一天额度用完", "max_results": 1})
    assert _auth(first.calls[0]) == f"Bearer {_KEY_A}"

    current["day"] = date(2026, 9, 25)
    second = _patch_http(monkeypatch, [_ok_search([])])
    with _context():
        raw = await anysearch_tool.anysearch_web_search.ainvoke({"query": "第二天再试", "max_results": 1})
    assert json.loads(raw)["ok"] is True
    assert len(second.calls) == 1
    assert _auth(second.calls[0]) == f"Bearer {_KEY_A}"


def test_resolve_dedup_order() -> None:
    """解析函数去重且保持顺序；多 key 非空时不读单 key。"""
    assert resolve_anysearch_keys("a, a, b", "c", "d") == ["a", "b"]
    assert resolve_anysearch_keys(None, "primary", "primary") == ["primary"]
    assert resolve_anysearch_keys("", "primary", "official") == ["primary", "official"]
