"""
AnySearch 供应商限速（DeepSeek Search 100 / Fetch 25 的 80%）单元测试。

覆盖：配置默认值、search/extract 分桶、注入 post_fn 时不启用、令牌桶实际降速。
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.domain.tools.anysearch.client import AnySearchClient
from backend.domain.tools.anysearch.config import AnySearchConfig
from backend.domain.tools.anysearch.pool import KeyRef


class _StubPool:
    """只满足 client 用到的接口。"""

    def __init__(self, cfg: AnySearchConfig) -> None:
        self._cfg = cfg

    def get_config(self) -> AnySearchConfig:
        return self._cfg

    async def acquire(self):
        return KeyRef(id=1, value="k1", label="#1", pool_tag="shared")

    def mark_result(self, key, **kw) -> None:  # noqa: ANN003
        pass

    def is_exhausted(self, key) -> bool:  # noqa: ANN001
        return False


def test_config_provider_defaults() -> None:
    """默认 provider 阈值 = DeepSeek 上限的 80%。"""
    cfg = AnySearchConfig.from_groups({})
    assert cfg.provider_search_qps == 80.0  # 0.8 * 100
    assert cfg.provider_fetch_qps == 20.0  # 0.8 * 25


def test_client_builds_split_buckets() -> None:
    """search / extract 各一个供应商限速桶。"""
    cfg = AnySearchConfig.from_groups({})
    cli = AnySearchClient(_StubPool(cfg))
    assert set(cli._provider_buckets) == {"/v1/search", "/v1/extract"}
    assert cli._provider_buckets["/v1/search"].qps == 80.0
    assert cli._provider_buckets["/v1/extract"].qps == 20.0


def test_post_fn_disables_provider_buckets() -> None:
    """注入 post_fn（单测 mock 传输）时不启用限速桶。"""
    cfg = AnySearchConfig.from_groups({})
    cli = AnySearchClient(_StubPool(cfg), post_fn=lambda *a: None)
    assert cli._provider_buckets == {}


def test_provider_throttle_slows_down() -> None:
    """provider_search_qps=2 时，4 次 search 应被排队降速（≥ ~1.0s）。"""
    cfg = AnySearchConfig.from_groups(
        {
            "rate": {"key_qps": 1000, "global_qps": 1000},
            "provider": {"provider_search_qps": 2, "provider_fetch_qps": 2},
        }
    )
    cli = AnySearchClient(_StubPool(cfg))

    async def fake_post(url, key, payload):
        return 200, {"code": 0, "data": {"results": []}}, ""

    cli._post_once = fake_post  # 绕过真实网络

    async def run() -> float:
        t0 = time.monotonic()
        for _ in range(4):
            r = await cli.search("q", max_results=1)
            assert r.get("ok"), r
        return time.monotonic() - t0

    elapsed = asyncio.run(run())
    # qps=2、burst=max(1,min(2,10))=2 → 前 2 次即时，后 2 次各等 ~0.5s → ≥ ~1.0s
    assert elapsed >= 0.9, f"未被降速：{elapsed:.2f}s"