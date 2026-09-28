"""只读候选按 host 去重后再认领，避免 PENDING 被整窗打成 RUNNING。"""
from __future__ import annotations

from radar_kb.host_pick import pick_distinct_host_tasks


def test_pick_skips_busy_and_duplicate_hosts() -> None:
    """忙碌站与窗口内重复 host 都应跳过，只留下 limit 条。"""
    candidates = [
        {"id": 1, "url": "https://a.com/1"},
        {"id": 2, "url": "https://b.com/1"},
        {"id": 3, "url": "https://a.com/2"},
        {"id": 4, "url": "https://c.com/1"},
        {"id": 5, "url": "https://d.com/1"},
    ]
    picked = pick_distinct_host_tasks(
        candidates, limit=2, busy_hosts={"b.com"}
    )
    ids = [int(t["id"]) for t in picked]
    assert ids == [1, 4]


def test_pick_empty_when_all_busy() -> None:
    candidates = [
        {"id": 1, "url": "https://a.com/1"},
        {"id": 2, "url": "https://a.com/2"},
    ]
    picked = pick_distinct_host_tasks(
        candidates, limit=8, busy_hosts={"a.com"}
    )
    assert picked == []
