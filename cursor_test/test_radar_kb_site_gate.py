"""
SiteGate 单测：同站串行、冷却在锁外、间隔落在配置区间。
"""
from __future__ import annotations

import asyncio
import time

from radar_kb.site_gate import GatePriority, SiteGate, normalize_host


def test_normalize_host() -> None:
    assert normalize_host("https://WWW.Example.COM/a") == "example.com"
    assert normalize_host("example.com") == "example.com"
    assert normalize_host("") == ""


def test_site_gate_serial_same_host() -> None:
    """同 host 两次 hold 不得重叠。"""
    gate = SiteGate(gap_min_sec=0.05, gap_max_sec=0.05, aging_after_discover=0)
    overlap = {"n": 0}
    holding = {"v": False}

    async def one() -> None:
        async with gate.hold_for_request("a.com", GatePriority.CONTENT):
            if holding["v"]:
                overlap["n"] += 1
            holding["v"] = True
            await asyncio.sleep(0.08)
            holding["v"] = False

    async def go() -> None:
        await asyncio.gather(one(), one())

    asyncio.run(go())
    assert overlap["n"] == 0


def test_site_gate_gap_after_release() -> None:
    """请求结束后下次开始前至少 gap_min。"""
    gate = SiteGate(gap_min_sec=0.12, gap_max_sec=0.12, aging_after_discover=0)
    ends: list[float] = []
    starts: list[float] = []

    async def one() -> None:
        async with gate.hold_for_request("b.com", GatePriority.CONTENT):
            starts.append(time.monotonic())
            await asyncio.sleep(0.02)
            ends.append(time.monotonic())

    async def go() -> None:
        await one()
        await one()

    asyncio.run(go())
    assert len(starts) == 2
    assert starts[1] - ends[0] >= 0.10


def test_site_gate_cross_host_parallel() -> None:
    """不同 host 可并行。"""
    gate = SiteGate(gap_min_sec=0.5, gap_max_sec=0.5, aging_after_discover=0)
    concurrent = {"max": 0, "cur": 0}

    async def one(host: str) -> None:
        async with gate.hold_for_request(host, GatePriority.CONTENT):
            concurrent["cur"] += 1
            concurrent["max"] = max(concurrent["max"], concurrent["cur"])
            await asyncio.sleep(0.08)
            concurrent["cur"] -= 1

    async def go() -> None:
        await asyncio.gather(one("x.com"), one("y.com"))

    t0 = time.monotonic()
    asyncio.run(go())
    elapsed = time.monotonic() - t0
    assert concurrent["max"] >= 2
    assert elapsed < 0.4
