"""
Agent 兜底闸门单测（内存 Store，不依赖 exhibition MySQL）。

覆盖设计文档 `ai_docs/26091605` §8.5 核心用例。
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from backend.domain.news_content.agent_fallback import AgentFallbackGuard
from backend.domain.news_content.agent_guard_store import (
    InMemoryAgentGuardStore,
    today_stat_date,
)


def _guard(
    store: InMemoryAgentGuardStore,
    *,
    quota: int = 30,
    system_max: int = 5,
    content_max: int = 1,
) -> AgentFallbackGuard:
    """构造注入内存 Store 的 Guard。"""
    return AgentFallbackGuard(
        enabled=True,
        daily_quota=quota,
        max_consecutive_failures=system_max,
        max_content_failures_per_site=content_max,
        store=store,
    )


@pytest.mark.asyncio
async def test_content_failures_do_not_trip_global() -> None:
    """连续多次可计入 content 失败不触发全局熔断；其它源仍可 allow。"""
    store = InMemoryAgentGuardStore()
    guard = _guard(store, system_max=5, content_max=1)
    # 5 个不同源各失败一次（可计入）
    for sid in range(1, 6):
        assert (await guard.allow(sid))[0]
        assert (await guard.try_consume_quota())[0]
        await guard.mark_result(
            success=False,
            source_url_id=sid,
            failure_kind="content",
            content_streak_eligible=True,
        )
    ok, _ = await guard.allow(99)
    assert ok is True
    assert await store.is_system_tripped(today_stat_date()) is False


@pytest.mark.asyncio
async def test_same_source_content_skip() -> None:
    """同源可计入 content 达阈后跳过；其它源不受影响。"""
    store = InMemoryAgentGuardStore()
    guard = _guard(store, content_max=1)

    assert (await guard.try_consume_quota())[0]
    await guard.mark_result(
        success=False,
        source_url_id=10,
        failure_kind="content",
        content_streak_eligible=True,
    )
    ok, reason = await guard.allow(10)
    assert ok is False
    assert "source_url_id=10" in reason

    ok2, _ = await guard.allow(11)
    assert ok2 is True


@pytest.mark.asyncio
async def test_system_failures_trip_global() -> None:
    """连续 system 失败达阈后全局熔断。"""
    store = InMemoryAgentGuardStore()
    guard = _guard(store, system_max=3)

    for _ in range(3):
        assert (await guard.allow(1))[0]
        assert (await guard.try_consume_quota())[0]
        await guard.mark_result(
            success=False,
            source_url_id=1,
            failure_kind="system",
            content_streak_eligible=False,
        )

    ok, reason = await guard.allow(2)
    assert ok is False
    assert "熔断" in reason


@pytest.mark.asyncio
async def test_transient_content_does_not_skip() -> None:
    """临时站点故障（content 但不可计入 streak）不推 skip。"""
    store = InMemoryAgentGuardStore()
    guard = _guard(store, content_max=1)

    assert (await guard.try_consume_quota())[0]
    await guard.mark_result(
        success=False,
        source_url_id=20,
        failure_kind="content",
        content_streak_eligible=False,
    )
    ok, _ = await guard.allow(20)
    assert ok is True


@pytest.mark.asyncio
async def test_missing_failure_kind_treated_as_system() -> None:
    """ok=False 且 kind 缺失时按 system 计。"""
    store = InMemoryAgentGuardStore()
    guard = _guard(store, system_max=1)

    assert (await guard.try_consume_quota())[0]
    await guard.mark_result(
        success=False,
        source_url_id=1,
        failure_kind=None,
        content_streak_eligible=False,
    )
    ok, _ = await guard.allow(2)
    assert ok is False


@pytest.mark.asyncio
async def test_success_clears_streaks() -> None:
    """成功清零系统与该源 content 计数。"""
    store = InMemoryAgentGuardStore()
    guard = _guard(store, content_max=2, system_max=5)

    assert (await guard.try_consume_quota())[0]
    await guard.mark_result(
        success=False,
        source_url_id=30,
        failure_kind="content",
        content_streak_eligible=True,
    )
    assert (await guard.try_consume_quota())[0]
    await guard.mark_result(
        success=True,
        source_url_id=30,
        failure_kind=None,
        content_streak_eligible=False,
    )
    # 清零后再失败一次不应跳过（阈值=2）
    assert (await guard.try_consume_quota())[0]
    await guard.mark_result(
        success=False,
        source_url_id=30,
        failure_kind="content",
        content_streak_eligible=True,
    )
    ok, _ = await guard.allow(30)
    assert ok is True


@pytest.mark.asyncio
async def test_quota_atomic_under_concurrency() -> None:
    """并发 try_consume_quota 总和不超过日配额。"""
    store = InMemoryAgentGuardStore()
    guard = _guard(store, quota=10)

    async def one() -> bool:
        ok, _ = await guard.try_consume_quota()
        return ok

    results = await asyncio.gather(*[one() for _ in range(40)])
    assert sum(1 for x in results if x) == 10
    assert sum(1 for x in results if not x) == 30


@pytest.mark.asyncio
async def test_cross_day_isolation() -> None:
    """跨日新旧行隔离：旧日熔断不影响新日（内存 Store 按 date 分桶）。"""
    store = InMemoryAgentGuardStore()
    yesterday = today_stat_date() - timedelta(days=1)
    # 直接写旧日 GLOBAL 为 tripped
    with store._lock:
        g = store._global_row(yesterday)
        g.system_tripped = True
        g.system_fail_streak = 9

    guard = _guard(store, system_max=5)
    ok, _ = await guard.allow(1)
    assert ok is True


@pytest.mark.asyncio
async def test_disabled_guard() -> None:
    """开关关闭时 allow 直接拒绝。"""
    store = InMemoryAgentGuardStore()
    guard = AgentFallbackGuard(
        enabled=False,
        daily_quota=30,
        max_consecutive_failures=5,
        store=store,
    )
    ok, reason = await guard.allow(1)
    assert ok is False
    assert "关闭" in reason
