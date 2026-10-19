"""AnySearch 独立包单元测试（不打外网、不连 DB）。

覆盖：配置合并、随机窗口、耗尽换新、failover 契约、限速降级。
运行：`python -m pytest cursor_test/test_anysearch_package.py -q`
或直接 `python cursor_test/test_anysearch_package.py`
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.domain.tools.anysearch import errors
from backend.domain.tools.anysearch.client import AnySearchClient
from backend.domain.tools.anysearch.config import DEFAULT_GROUPS, AnySearchConfig
from backend.domain.tools.anysearch.pool import AnySearchPool, KeyRef
from backend.domain.tools.anysearch.rate import AdaptiveLimiter, TokenBucket


def _ref(i: int, value: str, health: str = "available") -> KeyRef:
    """构造一枚测试用 key（负 id = 不触发 DB 回写）。"""
    return KeyRef(id=-i, value=value, label=f"#{i}", pool_tag="shared", health=health)


def test_config_merge() -> None:
    """DB 的 rate 覆盖默认，其余键保持默认。"""
    cfg = AnySearchConfig.from_groups({"rate": {"key_qps": 5}})
    assert cfg.key_qps == 5
    assert cfg.global_qps == DEFAULT_GROUPS["rate"]["global_qps"]
    assert cfg.sample_size == 10


def test_window_size_capped() -> None:
    """池 > sample_size 时窗口只保留 sample_size 把。"""
    p = AnySearchPool(owner="t")
    p.load_static([_ref(i, f"k{i}") for i in range(1, 21)], config=AnySearchConfig(lease_ttl_sec=0, sample_size=10))
    assert len(p._window) == 10


def test_pool_size_smaller_than_sample() -> None:
    """池 < sample_size 时窗口 = 全池。"""
    p = AnySearchPool(owner="t")
    p.load_static([_ref(i, f"k{i}") for i in range(1, 4)], config=AnySearchConfig(lease_ttl_sec=0, sample_size=10))
    assert len(p._window) == 3


def test_exhaust_drops_and_refills() -> None:
    """一把耗尽 → 移出窗口并随机补一把（池还有余量）。"""
    p = AnySearchPool(owner="t")
    p.load_static([_ref(i, f"k{i}") for i in range(1, 8)], config=AnySearchConfig(lease_ttl_sec=0, sample_size=3))
    target = p._window[0]
    p.mark_result(target, ok=False, health="exhausted", error_code=errors.ANYSEARCH_KEYS_EXHAUSTED)
    assert target.id not in p._window_ids
    assert len(p._window) == 3  # 已补一把
    assert p.has_live_key() is True


def test_all_exhausted_no_live_key() -> None:
    """全部耗尽 → 无可用 key，acquire 返回 None。"""
    p = AnySearchPool(owner="t")
    p.load_static([_ref(i, f"k{i}") for i in range(1, 3)], config=AnySearchConfig(lease_ttl_sec=0, sample_size=10))
    for k in list(p.snapshot().keys):
        p.mark_result(k, ok=False, health="exhausted")
    assert p.has_live_key() is False
    assert asyncio.run(p.acquire()) is None


def test_client_switches_key_on_402() -> None:
    """第一把 402 → 换一把成功（且两把不同）。"""
    p = AnySearchPool(owner="t")
    p.load_static([_ref(1, "kA"), _ref(2, "kB")], config=AnySearchConfig(lease_ttl_sec=0, sample_size=2, max_failover_keys=3))
    calls: list[str] = []

    async def post(url, headers, payload):
        key = headers["Authorization"].split()[-1]
        calls.append(key)
        if len(calls) == 1:
            return 402, None
        return 200, {"code": 0, "data": {"results": [{"title": "t", "url": "http://x"}]}}

    out = asyncio.run(AnySearchClient(p, post_fn=post).search("q"))
    assert out["ok"] is True and out["result_count"] == 1
    assert len(calls) == 2 and calls[0] != calls[1]


def test_client_all_402_exhausted() -> None:
    """两把都 402 → keys_exhausted。"""
    p = AnySearchPool(owner="t")
    p.load_static([_ref(1, "kA"), _ref(2, "kB")], config=AnySearchConfig(lease_ttl_sec=0, sample_size=2, max_failover_keys=3))

    async def post(url, headers, payload):
        return 402, None

    out = asyncio.run(AnySearchClient(p, post_fn=post).search("q"))
    assert out["ok"] is False and out["error_code"] == errors.ANYSEARCH_KEYS_EXHAUSTED


def test_client_429_rate_limited_not_fused() -> None:
    """429 → rate_limited，且 key 未被熔断（仍是 live）。"""
    p = AnySearchPool(owner="t")
    p.load_static([_ref(1, "kA")], config=AnySearchConfig(lease_ttl_sec=0, sample_size=1, max_failover_keys=1))

    async def post(url, headers, payload):
        return 429, None

    out = asyncio.run(AnySearchClient(p, post_fn=post).search("q"))
    assert out["error_code"] == errors.ANYSEARCH_RATE_LIMITED
    assert p.has_live_key() is True


def test_client_bad_request_no_fuse() -> None:
    """422 → bad_request，不熔断 key。"""
    p = AnySearchPool(owner="t")
    p.load_static([_ref(1, "kA")], config=AnySearchConfig(lease_ttl_sec=0, sample_size=1, max_failover_keys=1))

    async def post(url, headers, payload):
        return 422, None

    out = asyncio.run(AnySearchClient(p, post_fn=post).search("q"))
    assert out["error_code"] == errors.ANYSEARCH_BAD_REQUEST
    assert p.has_live_key() is True


def test_rate_degrade_and_recover() -> None:
    """429 乘性降速、平稳加性回升。"""
    lim = AdaptiveLimiter(nominal_qps=20, burst=20, degrade_factor=0.5, recover_step_qps=1, min_qps=1)
    lim.on_rate_limited()
    assert lim.effective_qps == 10
    lim.recover_tick()
    assert lim.effective_qps == 11


def test_token_bucket_burst() -> None:
    """桶内令牌足够时 acquire 立即返回。"""
    bucket = TokenBucket(qps=10, burst=3)

    async def go() -> None:
        for _ in range(3):
            await bucket.acquire()

    asyncio.run(go())


def _run_all() -> None:
    """无 pytest 时的简易运行器。"""
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"全部通过：{len(tests)} 项")


if __name__ == "__main__":
    _run_all()