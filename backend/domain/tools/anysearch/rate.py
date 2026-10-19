"""AnySearch 限速：令牌桶（每 key + 本机全局）+ AIMD 降级。

设计：`05-AnySearch-统一工具封装设计.md` §7。
- 「按当前机器」：不跨机协调，进程内即可。
- 429 时不熔断 key，只做冷却 + 降速；平稳后加性回升。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TokenBucket:
    """异步令牌桶：`acquire()` 取一个令牌，不足则等到够。"""

    def __init__(self, qps: float, burst: float) -> None:
        """
            Args:
                qps: 每秒补充速率
                burst: 桶容量（突发上限）
        """
        self._qps = max(0.1, float(qps))
        self._burst = max(1.0, float(burst))
        self._tokens = self._burst
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def qps(self) -> float:
        """当前速率。"""
        return self._qps

    def set_qps(self, qps: float) -> None:
        """调整速率（AIMD 用）。"""
        self._qps = max(0.1, float(qps))

    async def acquire(self, n: float = 1.0) -> None:
        """
            取 n 个令牌（不足则睡眠等待）。

            Args:
                n: 需要令牌数（默认 1）
        """
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self._burst, self._tokens + (now - self._last) * self._qps)
                self._last = now
                if self._tokens >= n:
                    self._tokens -= n
                    return
                await asyncio.sleep((n - self._tokens) / self._qps)


class AdaptiveLimiter:
    """带 AIMD 的自适应速率：默认按 nominal，429 时乘性降速、平稳时加性回升。"""

    def __init__(
        self,
        *,
        nominal_qps: float,
        burst: float,
        degrade_factor: float,
        recover_step_qps: float,
        min_qps: float,
    ) -> None:
        """
            Args:
                nominal_qps: 速率上限（天花板）
                burst: 桶容量
                degrade_factor: 429 时的乘性降速系数
                recover_step_qps: 每次回升的速率增量
                min_qps: 速率下限
        """
        self._nominal = max(0.1, float(nominal_qps))
        self._min = max(0.1, float(min_qps))
        self._effective = self._nominal
        self._degrade = min(0.99, max(0.05, float(degrade_factor)))
        self._recover_step = max(0.0, float(recover_step_qps))
        self._bucket = TokenBucket(self._effective, burst)

    @property
    def effective_qps(self) -> float:
        """当前有效速率。"""
        return self._effective

    async def acquire(self, n: float = 1.0) -> None:
        """取令牌（走当前有效速率）。"""
        await self._bucket.acquire(n)

    def on_rate_limited(self) -> None:
        """遇到 429：乘性降速（下限 min_qps）。"""
        new = max(self._min, self._effective * self._degrade)
        if abs(new - self._effective) > 1e-9:
            logger.warning("AnySearch 限速降级: %.2f → %.2f QPS", self._effective, new)
        self._effective = new
        self._bucket.set_qps(self._effective)

    def recover_tick(self) -> None:
        """平稳一段时间后：加性回升（不超过 nominal）。"""
        new = min(self._nominal, self._effective + self._recover_step)
        if new > self._effective:
            self._effective = new
            self._bucket.set_qps(self._effective)


class RateLimiter:
    """本机限速器：一个全局桶 + 每 key 一个桶。"""

    def __init__(
        self,
        *,
        key_qps: float,
        global_qps: float,
        burst: float,
        degrade_factor: float,
        recover_step_qps: float,
        min_qps: float,
    ) -> None:
        """
            按配置构造全局桶与每 key 桶的模板参数。
        """
        self._key_kwargs = dict(
            nominal_qps=key_qps,
            burst=burst,
            degrade_factor=degrade_factor,
            recover_step_qps=recover_step_qps,
            min_qps=min_qps,
        )
        self._global = AdaptiveLimiter(
            nominal_qps=global_qps,
            burst=max(burst, global_qps),
            degrade_factor=degrade_factor,
            recover_step_qps=recover_step_qps,
            min_qps=min_qps,
        )
        self._per_key: Dict[int, AdaptiveLimiter] = {}

    def _bucket_for(self, key_id: int) -> AdaptiveLimiter:
        """取或建某 key 的限速器。"""
        lim = self._per_key.get(key_id)
        if lim is None:
            lim = AdaptiveLimiter(**self._key_kwargs)
            self._per_key[key_id] = lim
        return lim

    async def acquire(self, key_id: int) -> None:
        """全局 + 该 key 各取一个令牌。"""
        await self._global.acquire(1.0)
        await self._bucket_for(key_id).acquire(1.0)

    def on_rate_limited(self, key_id: Optional[int] = None) -> None:
        """遇到 429：全局降速；给了 key_id 时该 key 也降速。"""
        self._global.on_rate_limited()
        if key_id is not None:
            self._bucket_for(key_id).on_rate_limited()

    def recover_all(self) -> None:
        """平稳回升（定时调用）。"""
        self._global.recover_tick()
        for lim in self._per_key.values():
            lim.recover_tick()

    def drop_key(self, key_id: int) -> None:
        """key 被移除窗口/耗尽时清掉其限速器。"""
        self._per_key.pop(key_id, None)


__all__ = ["TokenBucket", "AdaptiveLimiter", "RateLimiter"]