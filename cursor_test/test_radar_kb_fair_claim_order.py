"""
分组轮询认领：候选 id 应按 rn 层交错（先各站第 1 条，再第 2 条…）。
"""
from __future__ import annotations


def _fair_order(
    rows: list[tuple[int, int]],
    *,
    per_key: int,
    limit: int,
) -> list[int]:
    """
        纯 Python 复现 SQL 窗口语义，便于单测。

        Args:
            rows: (id, group_key) 列表，模拟 PENDING 集
            per_key: 每组最多取几条
            limit: 总上限

        Returns:
            认领顺序的 id 列表
    """
    by_group: dict[int, list[int]] = {}
    for tid, gkey in sorted(rows, key=lambda x: x[0]):
        by_group.setdefault(gkey, []).append(tid)

    layered: list[tuple[int, int]] = []  # (rn, id)
    for _gkey, ids in by_group.items():
        for rn, tid in enumerate(ids[:per_key], start=1):
            layered.append((rn, tid))
    layered.sort(key=lambda x: (x[0], x[1]))
    return [tid for _rn, tid in layered[:limit]]


def test_fair_claim_interleaves_groups_before_depth() -> None:
    """同站连续 id 入队时，结果应先跨站再加深。"""
    # 站 100: id 1,2,3；站 200: id 4,5,6；站 300: id 7,8
    rows = [
        (1, 100),
        (2, 100),
        (3, 100),
        (4, 200),
        (5, 200),
        (6, 200),
        (7, 300),
        (8, 300),
    ]
    ordered = _fair_order(rows, per_key=3, limit=6)
    # rn=1: 1,4,7；rn=2: 2,5,8 → 取满 6
    assert ordered == [1, 4, 7, 2, 5, 8]


def test_fair_claim_respects_per_key_cap() -> None:
    rows = [(i, 1) for i in range(1, 11)] + [(100 + i, 2) for i in range(1, 11)]
    ordered = _fair_order(rows, per_key=2, limit=200)
    assert ordered == [1, 101, 2, 102]
    assert len(ordered) == 4
