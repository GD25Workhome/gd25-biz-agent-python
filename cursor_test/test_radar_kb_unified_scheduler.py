"""
验证统一调度：发现优先、空表步长、让路不触发 1min。
"""
from __future__ import annotations

import time

from radar_kb.config import KbSettings
from radar_kb.scheduler import TaskScheduler


def _settings(*, empty_backoff: float = 60.0) -> KbSettings:
    return KbSettings(
        db_host="127.0.0.1",
        db_port=3306,
        db_user="u",
        db_password="p",
        db_name="db",
        tenant_id=None,
        worker_id="test",
        poll_interval_sec=10.0,
        poll_after_discover_sec=2.0,
        poll_after_content_sec=10.0,
        poll_idle_sec=8.0,
        empty_backoff_sec=empty_backoff,
        content_text_max_chars=1000,
        summary_max_chars=100,
        pdf_max_pages=10,
        cninfo_page_size=30,
        cninfo_max_pages=3,
        request_interval_sec=1.0,
        cninfo_request_interval_sec=1.0,
        cninfo_request_jitter_sec=0.0,
    )


def test_rest_seconds_by_work_kind() -> None:
    """发现短休、正文长休。"""
    sched = TaskScheduler(_settings(), "unified")
    assert sched._rest_seconds("discover") == 2.0
    assert sched._rest_seconds("content") == 10.0


def test_unified_prefers_discover_and_skips_content() -> None:
    """本轮发现有活时不再跑正文。"""
    sched = TaskScheduler(_settings(), "unified")
    calls: list[str] = []

    def fake_discover() -> bool:
        calls.append("discover")
        return True

    def fake_content():
        calls.append("content")
        return "work"

    sched._discover_once = fake_discover  # type: ignore[method-assign]
    sched._content_once = fake_content  # type: ignore[method-assign]

    assert sched._run_one_round() == "discover"
    assert calls == ["discover"]


def test_unified_falls_back_to_content_when_discover_empty() -> None:
    """发现无活时再跑正文。"""
    sched = TaskScheduler(_settings(), "unified")
    calls: list[str] = []

    def fake_discover() -> bool:
        calls.append("discover")
        return False

    def fake_content():
        calls.append("content")
        return "work"

    sched._discover_once = fake_discover  # type: ignore[method-assign]
    sched._content_once = fake_content  # type: ignore[method-assign]

    assert sched._run_one_round() == "content"
    assert calls == ["discover", "content"]


def test_unified_idle_when_both_empty() -> None:
    """两路皆空返回 idle，并写入空表步长。"""
    sched = TaskScheduler(_settings(empty_backoff=60.0), "unified")

    sched._discover_once = lambda: False  # type: ignore[method-assign]
    sched._content_once = lambda: "empty"  # type: ignore[method-assign]

    before = time.monotonic()
    assert sched._run_one_round() == "idle"
    assert sched._discover_next_at >= before + 59.0
    assert sched._content_next_at >= before + 59.0


def test_empty_backoff_skips_table_query() -> None:
    """空表步长未到时不调用 once（不查库）。"""
    sched = TaskScheduler(_settings(empty_backoff=60.0), "unified")
    now = time.monotonic()
    sched._discover_next_at = now + 30.0
    sched._content_next_at = now + 30.0
    calls: list[str] = []

    def boom_discover() -> bool:
        calls.append("discover")
        raise AssertionError("不应查发现表")

    def boom_content():
        calls.append("content")
        raise AssertionError("不应查正文表")

    sched._discover_once = boom_discover  # type: ignore[method-assign]
    sched._content_once = boom_content  # type: ignore[method-assign]

    assert sched._run_one_round() == "idle"
    assert calls == []
    # idle 休息应贴近剩余步长，而不是固定 8s
    remain = sched._idle_sleep_seconds()
    assert 25.0 <= remain <= 30.5


def test_discover_backoff_allows_content() -> None:
    """发现在空表冷却时，正文到点仍可查。"""
    sched = TaskScheduler(_settings(empty_backoff=60.0), "unified")
    now = time.monotonic()
    sched._discover_next_at = now + 60.0
    sched._content_next_at = 0.0
    calls: list[str] = []

    def boom_discover() -> bool:
        calls.append("discover")
        raise AssertionError("发现应被跳过")

    def fake_content():
        calls.append("content")
        return "work"

    sched._discover_once = boom_discover  # type: ignore[method-assign]
    sched._content_once = fake_content  # type: ignore[method-assign]

    assert sched._run_one_round() == "content"
    assert calls == ["content"]
    assert sched._content_next_at == 0.0


def test_content_yield_does_not_use_empty_backoff() -> None:
    """正文让路只用短延迟，不进入 60s 空表步长。"""
    sched = TaskScheduler(_settings(empty_backoff=60.0), "unified")
    sched._discover_once = lambda: False  # type: ignore[method-assign]
    sched._content_once = lambda: "yielded"  # type: ignore[method-assign]

    before = time.monotonic()
    assert sched._run_one_round() == "idle"
    # 发现空 → 60s；正文让路 → 约 2s（after_discover）
    assert sched._discover_next_at >= before + 59.0
    assert before + 1.5 <= sched._content_next_at <= before + 3.0
