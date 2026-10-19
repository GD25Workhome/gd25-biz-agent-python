"""AnySearch 动态配置：DB「一类一行 JSON」合并成一份扁平配置。

设计：`05-AnySearch-统一工具封装设计.md` §3.2 / §7 / §13.2。
- 内置默认 = 定案值；DB 里缺的类目/键用默认补齐；未知键忽略。
- 不含任何华院依赖，可独立使用。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, fields
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 内置默认（= 设计 §13.2 定案值）
DEFAULT_GROUPS: Dict[str, Dict[str, Any]] = {
    "pool": {
        "sample_size": 10,
        "max_failover_keys": 3,
        "lease_ttl_sec": 300,
        "pool_tag": "shared",
    },
    "rate": {
        "key_qps": 20,
        "global_qps": 50,
        "burst": 20,
        "degrade_factor": 0.5,
        "recover_step_qps": 1,
        "min_qps": 1,
    },
    "provider": {
        # DeepSeek 查询上限的 80%（Search 100 / Fetch 25）——工具内部降速阈值
        "provider_search_qps": 80,
        "provider_fetch_qps": 20,
    },
    "health": {
        "default_daily_quota": 1000,
        "cooldown_429_ms": 30000,
        "auto_retry_max_days": 2,
        "retry_log_max": 10,
        "reset_tz": "Asia/Shanghai",
    },
    "misc": {
        "enabled": True,
        "refresh_interval_sec": 60,
    },
}


@dataclass
class AnySearchConfig:
    """扁平配置：所有类目的键汇到一处，供各模块直接读。"""

    # pool
    sample_size: int = 10
    max_failover_keys: int = 3
    lease_ttl_sec: int = 300
    pool_tag: str = "shared"
    # rate
    key_qps: float = 20.0
    global_qps: float = 50.0
    burst: float = 20.0
    degrade_factor: float = 0.5
    recover_step_qps: float = 1.0
    min_qps: float = 1.0
    # provider（DeepSeek 查询上限的 80%：Search 100 / Fetch 25；工具内部降速）
    provider_search_qps: float = 80.0
    provider_fetch_qps: float = 20.0
    # health
    default_daily_quota: int = 1000
    cooldown_429_ms: int = 30000
    auto_retry_max_days: int = 2
    retry_log_max: int = 10
    reset_tz: str = "Asia/Shanghai"
    # misc
    enabled: bool = True
    refresh_interval_sec: int = 60

    @classmethod
    def from_groups(cls, groups: Optional[Dict[str, Dict[str, Any]]]) -> "AnySearchConfig":
        """
            用 DB 的 {类别: {键: 值}} 覆盖默认，构造扁平配置。

            Args:
                groups: 形如 {"rate": {"key_qps": 10}, ...}；None/空表示全用默认

            Returns:
                AnySearchConfig
        """
        merged: Dict[str, Any] = {}
        for group in DEFAULT_GROUPS.values():
            merged.update(group)
        for group in (groups or {}).values():
            if isinstance(group, dict):
                merged.update(group)

        known = {f.name for f in fields(cls)}
        kwargs: Dict[str, Any] = {}
        for k, v in merged.items():
            if k not in known:
                logger.debug("AnySearch 配置未知键已忽略: %s", k)
                continue
            kwargs[k] = v
        # 类型收敛（DB 里 JSON 可能是字符串/数字混用）
        cfg = cls(**kwargs)
        cfg.sample_size = max(1, int(cfg.sample_size))
        cfg.max_failover_keys = max(1, int(cfg.max_failover_keys))
        cfg.lease_ttl_sec = max(0, int(cfg.lease_ttl_sec))
        cfg.key_qps = max(0.1, float(cfg.key_qps))
        cfg.global_qps = max(0.1, float(cfg.global_qps))
        cfg.burst = max(1.0, float(cfg.burst))
        cfg.degrade_factor = min(0.99, max(0.05, float(cfg.degrade_factor)))
        cfg.recover_step_qps = max(0.0, float(cfg.recover_step_qps))
        cfg.min_qps = max(0.1, float(cfg.min_qps))
        cfg.provider_search_qps = max(0.1, float(cfg.provider_search_qps))
        cfg.provider_fetch_qps = max(0.1, float(cfg.provider_fetch_qps))
        cfg.default_daily_quota = max(1, int(cfg.default_daily_quota))
        cfg.retry_log_max = max(1, int(cfg.retry_log_max))
        cfg.refresh_interval_sec = max(1, int(cfg.refresh_interval_sec))
        return cfg


def parse_group_json(raw: Any) -> Dict[str, Any]:
    """
        解析单个类目的 config_json（容忍非法 JSON，失败返回空 dict）。

        Args:
            raw: TEXT 字段内容（JSON 字符串）

        Returns:
            解析后的 dict；失败为空 dict
    """
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        obj = json.loads(str(raw))
        return obj if isinstance(obj, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("AnySearch config_json 解析失败，按默认处理: %s", exc)
        return {}


__all__ = ["AnySearchConfig", "DEFAULT_GROUPS", "parse_group_json"]