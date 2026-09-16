"""
同站限速器（网站礼貌抓取）。

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md`
          §3.1（两段式 worker）/ §8-6（限速内移到 gd25 worker 内实现）

口径：**按站点**（task 表的 `source_url_id`，即 `radar_company_source_url.id`）算最小间隔，
不是按域名 —— 同一个域名下的不同栏目在 exhibition 侧就是不同 source_url，
按 source_url 更保守（宁可多等，不要打崩对方站）。
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict

# 未提供 site_key 时的兜底键（仍受最小间隔约束，不会退化成无限速）
GLOBAL_SITE_KEY = "__global__"


class SiteRateLimiter:
    """
    异步安全的按站点最小间隔限速器。

    语义：同一 `site_key` 的两次 `acquire()` 间隔 ≥ `min_interval` 秒；
    不同 `site_key` 之间互不影响。

    ⚠️ 只在**单进程内**生效（多实例各限各的）。多实例部署下等效间隔会变成
    `min_interval / 实例数`；当前设计是单 worker 常驻（§7 P0），够用。
    """

    def __init__(self, min_interval: float) -> None:
        """
        Args:
            min_interval: 同站两次抓取的最小间隔（秒），<=0 表示不限速
        """
        self.min_interval = max(0.0, float(min_interval))
        self._last_at: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, site_key: str | None) -> None:
        """
        取一次「抓取许可」；必要时 sleep 到满足最小间隔。

        Args:
            site_key: 站点标识（用 task 的 source_url_id）；None/空走全局键
        """
        if self.min_interval <= 0:
            return
        key = str(site_key or GLOBAL_SITE_KEY)
        async with self._lock:
            now = time.monotonic()
            last = self._last_at.get(key)
            wait = 0.0
            if last is not None:
                wait = self.min_interval - (now - last)
            # 先占用时间片再放锁：保证并发调用者按序排队，不会同时穿透
            self._last_at[key] = now + max(0.0, wait)
        if wait > 0:
            await asyncio.sleep(wait)

    def reset(self) -> None:
        """清空记录（测试用）。"""
        self._last_at.clear()
