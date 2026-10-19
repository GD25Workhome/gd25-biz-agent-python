"""AnySearch 凭证池：快照缓存 + 纯随机 ≤N 窗口 + 租约 + 健康态。

设计：`05-AnySearch-统一工具封装设计.md` §4/§5/§6。
- 与华院无关：只依赖本包的 store/config/rate。
- 进程内维护随机窗口；key/配置的多副本共享状态在 DB。
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import socket
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.domain.tools.anysearch import store
from backend.domain.tools.anysearch.config import AnySearchConfig
from backend.domain.tools.anysearch.rate import RateLimiter

logger = logging.getLogger(__name__)

# 健康态
HEALTH_AVAILABLE = "available"
HEALTH_EXHAUSTED = "exhausted"
HEALTH_INVALID = "invalid"
HEALTH_COOLING = "cooling"

_UNUSABLE_HEALTH = (HEALTH_EXHAUSTED, HEALTH_INVALID)


def _process_owner() -> str:
    """进程唯一租约标识：host:pid:rand6（防同机多进程撞名）。"""
    host = ""
    try:
        host = socket.gethostname()
    except Exception:  # noqa: BLE001
        host = "host"
    rand = os.urandom(3).hex()
    return f"{host[:32]}:{os.getpid()}:{rand}"[:64]


@dataclass
class KeyRef:
    """池内一枚 key 的运行态。"""

    id: int
    value: str
    label: str
    pool_tag: str
    health: str = HEALTH_AVAILABLE
    cooldown_until: Optional[datetime] = None
    daily_quota: int = 1000
    used_today: int = 0
    max_qps: Optional[float] = None


@dataclass
class Snapshot:
    """一次加载的不可变快照。"""

    keys: List[KeyRef] = field(default_factory=list)
    config: AnySearchConfig = field(default_factory=AnySearchConfig)
    version: str = ""
    source: str = "empty"
    loaded_at: float = 0.0


class AnySearchPool:
    """凭证池：负责「从 DB/env 出快照 → 随机窗口取 key → 租约/健康态回写」。"""

    def __init__(self, owner: Optional[str] = None) -> None:
        """
            Args:
                owner: 租约持有者标识；缺省用进程唯一标识
        """
        self.owner = owner or _process_owner()
        self._snap = Snapshot()
        self._window: List[KeyRef] = []
        self._window_ids: set[int] = set()
        self._exhausted_today: Dict[int, date] = {}
        self._rate: Optional[RateLimiter] = None
        self._lock = asyncio.Lock()
        self._bg: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    # ------------------------------------------------------------ 快照
    def get_config(self) -> AnySearchConfig:
        """当前配置（未加载时用默认）。"""
        return self._snap.config

    def snapshot(self) -> Snapshot:
        """当前快照。"""
        return self._snap

    def _fresh(self) -> bool:
        """快照是否仍在 TTL 内。"""
        ttl = max(1, int(self._snap.config.refresh_interval_sec))
        return (time.monotonic() - self._snap.loaded_at) < ttl

    def _build_refs(self, rows: List[store.KeyRow], cfg: AnySearchConfig) -> List[KeyRef]:
        """DB 行 → KeyRef；pool_tag 不匹配则跳过（默认 shared 等于不过滤）。"""
        refs: List[KeyRef] = []
        for r in rows:
            if not r.key_value:
                continue
            if cfg.pool_tag and cfg.pool_tag != "shared" and r.pool_tag != cfg.pool_tag:
                continue
            refs.append(
                KeyRef(
                    id=r.id,
                    value=r.key_value,
                    label=r.key_label or store.key_label(r.id, r.key_value),
                    pool_tag=r.pool_tag,
                    health=r.health,
                    daily_quota=r.daily_quota,
                    used_today=r.used_today,
                    max_qps=r.max_qps,
                )
            )
        return refs

    def _env_refs(self) -> List[KeyRef]:
        """DB 无 key 时用 .env 引导（id 用负序号，避免与 DB id 混淆）。"""
        refs: List[KeyRef] = []
        for i, key in enumerate(store.env_seed_keys(), start=1):
            refs.append(
                KeyRef(id=-i, value=key, label=store.key_label(i, key), pool_tag="env")
            )
        return refs

    def reload(self, force: bool = False) -> Snapshot:
        """
            重新加载快照（TTL 内且非 force 直接复用）。

            Args:
                force: 忽略 TTL 强制重载

            Returns:
                当前快照
        """
        if not force and self._fresh() and self._snap.source != "empty":
            return self._snap

        groups = store.load_config_groups()
        cfg = AnySearchConfig.from_groups(groups)
        rows = store.load_key_rows()
        if rows:
            refs, source = self._build_refs(rows, cfg), "db"
        else:
            refs, source = self._env_refs(), ("env" if store.env_seed_keys() else "empty")

        snap = Snapshot(
            keys=refs,
            config=cfg,
            version=store.version_probe(),
            source=source,
            loaded_at=time.monotonic(),
        )
        self._swap(snap)
        logger.info(
            "AnySearch 池快照加载 source=%s keys=%d sample=%s owner=%s",
            source, len(refs), cfg.sample_size, self.owner,
        )
        return snap

    def load_static(
        self,
        keys: List[KeyRef],
        *,
        config: Optional[AnySearchConfig] = None,
        source: str = "static",
    ) -> Snapshot:
        """
            用给定的 key 列表直接装载快照（不走 DB）。

            用途：单测、env-only 模式、旁路验证。

            Args:
                keys: KeyRef 列表
                config: 配置；缺省沿用当前
                source: 来源标签

            Returns:
                新快照
        """
        snap = Snapshot(
            keys=list(keys),
            config=config or self._snap.config,
            version="",
            source=source,
            loaded_at=time.monotonic(),
        )
        self._swap(snap)
        return snap

    def _swap(self, snap: Snapshot) -> None:
        """原子替换快照 + 重建窗口与限速器（保留本地 exhausted 标记）。"""
        self._snap = snap
        cfg = snap.config
        self._rate = RateLimiter(
            key_qps=cfg.key_qps,
            global_qps=cfg.global_qps,
            burst=cfg.burst,
            degrade_factor=cfg.degrade_factor,
            recover_step_qps=cfg.recover_step_qps,
            min_qps=cfg.min_qps,
        )
        by_id = {k.id: k for k in snap.keys}
        # 保留仍在池内的窗口成员（沿用其最新健康态），其余丢弃
        self._window = [by_id[i] for i in self._window_ids if i in by_id]
        self._window_ids = {k.id for k in self._window}
        self._refill()

    # ------------------------------------------------------------ 窗口
    def _today(self) -> date:
        """上海日历日（0 点重置基准）。"""
        cfg = self._snap.config
        try:
            tz = ZoneInfo(cfg.reset_tz or "Asia/Shanghai")
        except Exception:  # noqa: BLE001
            tz = ZoneInfo("Asia/Shanghai")
        return datetime.now(tz).date()

    def _is_locally_exhausted(self, key_id: int) -> bool:
        """该 key 是否「本地记的当日耗尽/失效」（0 点自动失效该标记）。"""
        day = self._exhausted_today.get(key_id)
        if day is None:
            return False
        if day != self._today():
            self._exhausted_today.pop(key_id, None)
            return False
        return True

    def _refill(self) -> None:
        """把随机窗口补到 sample_size（纯随机，跳过已耗尽/冷却中/不在池内的）。"""
        cfg = self._snap.config
        target = max(1, min(int(cfg.sample_size), 1000))
        if len(self._window) >= target:
            return
        candidates = [
            k
            for k in self._snap.keys
            if k.id not in self._window_ids
            and not self._is_locally_exhausted(k.id)
            and k.health in (HEALTH_AVAILABLE, HEALTH_COOLING)
        ]
        random.shuffle(candidates)
        for k in candidates:
            if len(self._window) >= target:
                break
            self._window.append(k)
            self._window_ids.add(k.id)

    def _live_keys(self) -> List[KeyRef]:
        """当前认为可用的 key（快照内、非本地耗尽）。"""
        return [
            k
            for k in self._snap.keys
            if not self._is_locally_exhausted(k.id) and k.health != HEALTH_INVALID
        ]

    def has_live_key(self) -> bool:
        """是否还有可用 key（同步；供节点/调度做降级判断）。"""
        cfg = self._snap.config
        if not cfg.enabled:
            return False
        if self._snap.source == "empty" and not self._snap.keys:
            self.reload(force=True)
        return bool(self._live_keys())

    # ------------------------------------------------------------ 取用
    async def acquire(self) -> Optional[KeyRef]:
        """
            取一枚 key：随机窗口 → 限速 → 抢租约。

            Returns:
                KeyRef；无可用返回 None
        """
        snap = self.reload()
        cfg = snap.config
        if not cfg.enabled:
            return None

        async with self._lock:
            self._refill()
            if not self._window:
                return None
            order = list(self._window)
            random.shuffle(order)
            for key in order:
                if self._is_locally_exhausted(key.id):
                    continue
                if key.health == HEALTH_COOLING and key.cooldown_until and key.cooldown_until > datetime.now():
                    continue
                # 租约（lease_ttl_sec>0 且非 env 引导 key 才抢；env key 无 DB 行）
                if cfg.lease_ttl_sec > 0 and key.id > 0:
                    got = await store.claim_lease_async(key.id, self.owner, cfg.lease_ttl_sec)
                    if not got:
                        continue
                if self._rate is not None:
                    await self._rate.acquire(key.id)
                return key
            return None

    # ------------------------------------------------------------ 结果回写
    def mark_result(
        self,
        key: KeyRef,
        *,
        ok: bool,
        health: Optional[str] = None,
        error_code: Optional[str] = None,
        reason: Optional[str] = None,
        cooldown_ms: Optional[int] = None,
    ) -> None:
        """
            记录一次调用结果，更新健康态（本地 + 异步回写 DB）。

            Args:
                key: 本次使用的 key
                ok: 是否成功
                health: 目标健康态（429→cooling / 402→exhausted / 401·403→invalid）
                error_code: error_code 契约值
                reason: 说明（已脱敏）
                cooldown_ms: 冷却毫秒（cooling 用）
        """
        cfg = self._snap.config
        if ok:
            key.health = HEALTH_AVAILABLE
            key.cooldown_until = None
            if key.id > 0:
                asyncio.create_task(store.mark_health_async(key.id, health=HEALTH_AVAILABLE, success=True))
            return

        target = health or HEALTH_AVAILABLE
        if target == HEALTH_COOLING and cooldown_ms:
            key.cooldown_until = datetime.now() + timedelta(milliseconds=int(cooldown_ms))
        key.health = target

        if key.id > 0:
            cooldown_until = key.cooldown_until
            if target in _UNUSABLE_HEALTH:
                cooldown_until = self._next_midnight()
            asyncio.create_task(
                store.mark_health_async(
                    key.id,
                    health=target,
                    reason=reason,
                    error_code=error_code,
                    cooldown_until=cooldown_until,
                )
            )

        if target in _UNUSABLE_HEALTH:
            self._drop(key.id)
            self._exhausted_today[key.id] = self._today()
            self._refill()  # 立即随机补一把

    def _drop(self, key_id: int) -> None:
        """把 key 移出窗口（并清理其限速器）。"""
        self._window = [k for k in self._window if k.id != key_id]
        self._window_ids.discard(key_id)
        if self._rate is not None:
            self._rate.drop_key(key_id)

    def on_rate_limited(self, key_id: Optional[int] = None) -> None:
        """429：触发全局（及该 key）降速。"""
        if self._rate is not None:
            self._rate.on_rate_limited(key_id)

    def _next_midnight(self) -> datetime:
        """下一个本地 0 点（exhausted/invalid 冷却到此时）。"""
        cfg = self._snap.config
        try:
            tz = ZoneInfo(cfg.reset_tz or "Asia/Shanghai")
        except Exception:  # noqa: BLE001
            tz = ZoneInfo("Asia/Shanghai")
        now = datetime.now(tz)
        tomorrow = (now + timedelta(days=1)).date()
        return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=tz).replace(tzinfo=None)

    async def release_all(self) -> None:
        """释放本进程持有的所有租约（退出时调用）。"""
        cfg = self._snap.config
        if cfg.lease_ttl_sec <= 0:
            return
        for key in list(self._window):
            if key.id > 0:
                try:
                    await store.release_lease_async(key.id, self.owner)
                except Exception:  # noqa: BLE001
                    pass

    # ------------------------------------------------------------ 后台刷新
    def start_background(self) -> None:
        """启动后台定时刷新（需在事件循环内调用）。"""
        if self._bg is not None:
            return
        self._stop = asyncio.Event()

        async def _loop() -> None:
            while not self._stop.is_set():
                cfg = self._snap.config
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=max(1, int(cfg.refresh_interval_sec))
                    )
                    break
                except asyncio.TimeoutError:
                    pass
                try:
                    ver = await store.version_probe_async()
                    if ver and ver != self._snap.version:
                        self.reload(force=True)
                    if self._rate is not None:
                        self._rate.recover_all()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("AnySearch 后台刷新异常: %s", exc)

        self._bg = asyncio.create_task(_loop())
        logger.info("AnySearch 池后台刷新已启动 interval=%ss", self._snap.config.refresh_interval_sec)

    def stop_background(self) -> None:
        """停止后台刷新。"""
        if self._bg is not None:
            self._stop.set()
            self._bg = None


_pool: Optional[AnySearchPool] = None


def get_anysearch_pool() -> AnySearchPool:
    """进程内共享池单例。"""
    global _pool
    if _pool is None:
        _pool = AnySearchPool()
    return _pool


def has_live_key() -> bool:
    """兼容旧调用：进程池是否还有可用 key。"""
    return get_anysearch_pool().has_live_key()


__all__ = [
    "AnySearchPool",
    "KeyRef",
    "Snapshot",
    "get_anysearch_pool",
    "has_live_key",
    "HEALTH_AVAILABLE",
    "HEALTH_EXHAUSTED",
    "HEALTH_INVALID",
    "HEALTH_COOLING",
]