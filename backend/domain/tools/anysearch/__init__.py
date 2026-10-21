"""AnySearch 独立工具包：凭证池 + 动态配置 + 限速 + failover。

定位：**只负责调用 AnySearch，与其它任何模块无关**（不 import 华院上下文）。
设计：`华院Agent设计/00-当前技术设计-总览.md` §1.3（AnySearch 可选工具，未挂 flow）

分层：
  - `errors`  error_code 常量（沿用 260924-01 契约）
  - `config`  动态配置（DB 一类一行 JSON → 扁平配置）
  - `store`   读写 exhibition MySQL 的 radar_anysearch_key / radar_anysearch_config
  - `rate`    令牌桶（每 key + 本机全局 + AIMD 降级）
  - `pool`    快照缓存 + 随机 ≤N 窗口 + 租约 + 健康态
  - `client`  纯传输 + failover（search / extract）

华院层适配（配额 + enrichment）见 `backend/domain/tools/anysearch_flow.py`（Phase 2）。
"""
from backend.domain.tools.anysearch.config import AnySearchConfig, DEFAULT_GROUPS
from backend.domain.tools.anysearch.errors import (
    ANYSEARCH_BAD_REQUEST,
    ANYSEARCH_KEYS_EXHAUSTED,
    ANYSEARCH_RATE_LIMITED,
    ANYSEARCH_TIMEOUT,
    ANYSEARCH_UPSTREAM_ERROR,
)
from backend.domain.tools.anysearch.pool import AnySearchPool, KeyRef, get_anysearch_pool
from backend.domain.tools.anysearch.client import AnySearchClient

__all__ = [
    "AnySearchConfig",
    "DEFAULT_GROUPS",
    "AnySearchPool",
    "AnySearchClient",
    "KeyRef",
    "get_anysearch_pool",
    "ANYSEARCH_KEYS_EXHAUSTED",
    "ANYSEARCH_BAD_REQUEST",
    "ANYSEARCH_RATE_LIMITED",
    "ANYSEARCH_UPSTREAM_ERROR",
    "ANYSEARCH_TIMEOUT",
]