"""
正文任务 Frontier（P1）：按礼貌键分队列 + 到点再取。

设计文档：ai_docs/26091801-正文任务域名打散调度方案.md
"""
from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterable, List, Literal, Optional
from urllib.parse import urlparse

PoliteKeyMode = Literal["source_url_id", "host", "company_id"]


def extract_host(url: str) -> str:
    """从 URL 提取归一化 host（小写，去 www. 前缀可选保留）。"""
    text = (url or "").strip()
    if not text:
        return ""
    try:
        host = (urlparse(text).hostname or "").strip().lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def polite_key_for_task(task: dict[str, Any], mode: PoliteKeyMode) -> str:
    """
        计算任务礼貌键。

        Args:
            task: content_task 行
            mode: source_url_id | host | company_id

        Returns:
            非空字符串键；缺失时回退 host → company → global
    """
    if mode == "source_url_id":
        sid = int(task.get("source_url_id") or 0)
        if sid > 0:
            return f"src:{sid}"
    if mode == "company_id":
        cid = int(task.get("company_id") or 0)
        if cid > 0:
            return f"co:{cid}"
    host = extract_host(str(task.get("url") or ""))
    if host:
        return f"host:{host}"
    cid = int(task.get("company_id") or 0)
    if cid > 0:
        return f"co:{cid}"
    return "global"


@dataclass(frozen=True)
class FrontierPop:
    """
        一次弹出结果。

        task 非空表示可立刻执行；wait_sec>0 且 task 为空表示需先睡再调 pop。
    """

    task: Optional[dict[str, Any]]
    key: Optional[str]
    wait_sec: float


class ContentFrontier:
    """
        内存级 URL Frontier：每个礼貌键一条 FIFO，调度只取已冷却键的队头。
    """

    def __init__(
        self,
        *,
        polite_key_mode: PoliteKeyMode = "source_url_id",
        same_key_gap_min_sec: float = 5.0,
        same_key_gap_max_sec: float = 10.0,
        site_min_interval_sec: float = 0.0,
    ) -> None:
        self.polite_key_mode = polite_key_mode
        self.same_key_gap_min_sec = max(0.0, float(same_key_gap_min_sec))
        self.same_key_gap_max_sec = max(
            self.same_key_gap_min_sec, float(same_key_gap_max_sec)
        )
        self.site_min_interval_sec = max(0.0, float(site_min_interval_sec))
        self._queues: Dict[str, Deque[dict[str, Any]]] = {}
        self._next_allowed: Dict[str, float] = {}
        self._last_key: Optional[str] = None
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def empty(self) -> bool:
        """是否无待执行任务。"""
        return self._size <= 0

    def key_count(self) -> int:
        """当前非空礼貌键数量。"""
        return len(self._queues)

    def add_tasks(self, tasks: Iterable[dict[str, Any]]) -> int:
        """
            将已认领（RUNNING）任务按礼貌键入队；组内保持传入顺序（claim 已 id ASC）。

            Returns:
                实际入队条数
        """
        added = 0
        for task in tasks:
            key = polite_key_for_task(task, self.polite_key_mode)
            q = self._queues.get(key)
            if q is None:
                q = deque()
                self._queues[key] = q
                # 新键默认可立刻取；若该键曾抓过，保留原 next_allowed
                self._next_allowed.setdefault(key, 0.0)
            q.append(task)
            added += 1
            self._size += 1
        return added

    def pop_ready(self, now: Optional[float] = None) -> FrontierPop:
        """
            取出一条已冷却任务；若仅有未冷却任务则返回 wait_sec。

            Args:
                now: 单调时钟；默认 time.monotonic()
        """
        if self._size <= 0:
            return FrontierPop(task=None, key=None, wait_sec=0.0)

        ts = float(now if now is not None else time.monotonic())
        ready: List[str] = []
        earliest_wait: Optional[float] = None

        for key, queue in self._queues.items():
            if not queue:
                continue
            allowed = float(self._next_allowed.get(key, 0.0))
            if allowed <= ts:
                ready.append(key)
            else:
                wait = allowed - ts
                if earliest_wait is None or wait < earliest_wait:
                    earliest_wait = wait

        if not ready:
            return FrontierPop(
                task=None,
                key=None,
                wait_sec=max(0.05, float(earliest_wait or 0.5)),
            )

        # 优先换键，避免与上一条同站
        pick = ready[0]
        if self._last_key is not None:
            for key in ready:
                if key != self._last_key:
                    pick = key
                    break

        queue = self._queues[pick]
        task = queue.popleft()
        self._size -= 1
        if not queue:
            del self._queues[pick]
        self._last_key = pick
        return FrontierPop(task=task, key=pick, wait_sec=0.0)

    def mark_fetched(self, key: str, now: Optional[float] = None) -> float:
        """
            记录某键刚抓完，写入下次可取时间。

            Returns:
                实际采用的间隔秒数
        """
        ts = float(now if now is not None else time.monotonic())
        gap = self._compute_gap()
        self._next_allowed[key] = ts + gap
        return gap

    def _compute_gap(self) -> float:
        """同站间隔：配置随机区间与站点最小间隔取 max。"""
        if self.same_key_gap_max_sec <= self.same_key_gap_min_sec:
            base = self.same_key_gap_min_sec
        else:
            base = random.uniform(self.same_key_gap_min_sec, self.same_key_gap_max_sec)
        return max(base, self.site_min_interval_sec)

    def peek_stats(self) -> dict[str, Any]:
        """调试用快照。"""
        return {
            "size": self._size,
            "keys": self.key_count(),
            "last_key": self._last_key,
        }
