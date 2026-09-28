"""正文候选按 host 去重，供认领前筛选。"""
from __future__ import annotations

from typing import Any

from radar_kb.site_gate import host_from_task


def pick_distinct_host_tasks(
    candidates: list[dict[str, Any]],
    *,
    limit: int,
    busy_hosts: set[str],
) -> list[dict[str, Any]]:
    """
        从只读候选里挑不同 host，最多 ``limit`` 条；不改库。

        Args:
            candidates: 公平窗口内的 PENDING 行
            limit: 本轮真正要认领的条数
            busy_hosts: 当前已占槽的 host

        Returns:
            选中的候选行（顺序与公平窗口一致）
    """
    picked: list[dict[str, Any]] = []
    seen = set(busy_hosts)
    cap = max(0, int(limit))
    for task in candidates:
        if len(picked) >= cap:
            break
        host = host_from_task(task) or "__global__"
        if host in seen:
            continue
        picked.append(task)
        seen.add(host)
    return picked
