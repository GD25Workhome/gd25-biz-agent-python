"""
正文 ContentFrontier（P1）单测：多站交错、同站冷却。
"""
from __future__ import annotations

from radar_kb.content_frontier import ContentFrontier, polite_key_for_task


def _task(tid: int, source_url_id: int, company_id: int = 1, url: str = "") -> dict:
    return {
        "id": tid,
        "source_url_id": source_url_id,
        "company_id": company_id,
        "url": url or f"https://site{source_url_id}.example.com/a/{tid}",
        "source_kind": "news_html",
    }


def test_polite_key_source_url_id() -> None:
    assert polite_key_for_task(_task(1, 9), "source_url_id") == "src:9"
    assert polite_key_for_task(
        _task(1, 0, url="https://WWW.Foo.com/x"), "host"
    ) == "host:foo.com"


def test_frontier_interleaves_different_keys() -> None:
    """同站长串入队后，弹出应优先换站（不打 mark 时各键均就绪）。"""
    frontier = ContentFrontier(
        polite_key_mode="source_url_id",
        same_key_gap_min_sec=5.0,
        same_key_gap_max_sec=5.0,
        site_min_interval_sec=0.0,
    )
    tasks = [
        _task(1, 100),
        _task(2, 100),
        _task(3, 100),
        _task(4, 200),
        _task(5, 200),
        _task(6, 200),
    ]
    frontier.add_tasks(tasks)
    keys: list[str] = []
    for _ in range(6):
        pop = frontier.pop_ready(now=1000.0)
        assert pop.task is not None
        assert pop.key is not None
        keys.append(pop.key)
    same_adjacent = sum(1 for a, b in zip(keys, keys[1:]) if a == b)
    assert same_adjacent == 0, keys
    assert keys.count("src:100") == 3
    assert keys.count("src:200") == 3


def test_frontier_same_key_requires_wait() -> None:
    """仅一站时：取出后需等待 gap。"""
    frontier = ContentFrontier(
        polite_key_mode="source_url_id",
        same_key_gap_min_sec=8.0,
        same_key_gap_max_sec=8.0,
        site_min_interval_sec=2.0,
    )
    frontier.add_tasks([_task(1, 7), _task(2, 7)])
    now = 50.0
    first = frontier.pop_ready(now=now)
    assert first.task is not None
    gap = frontier.mark_fetched(first.key or "", now=now)
    assert gap == 8.0  # max(8, 2)

    second = frontier.pop_ready(now=now + 1.0)
    assert second.task is None
    assert second.wait_sec > 0

    ready = frontier.pop_ready(now=now + gap)
    assert ready.task is not None
    assert int(ready.task["id"]) == 2
