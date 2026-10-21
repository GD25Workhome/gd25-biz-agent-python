"""error_code 契约（调用方只认这些字符串；原 260924-01 契约文档已随文档清理删除）。"""
from __future__ import annotations

# 无可用 key，或换完仍全被拒（401/402/带 request_id 的 403）
ANYSEARCH_KEYS_EXHAUSTED = "anysearch_keys_exhausted"
# 400 / 415 / 422，或无 request_id 的 403（请求本身有问题，不熔断 key）
ANYSEARCH_BAD_REQUEST = "anysearch_bad_request"
# 429 限流（不熔断、不换 key）
ANYSEARCH_RATE_LIMITED = "anysearch_rate_limited"
# 5xx，或 2xx 但业务 code != 0
ANYSEARCH_UPSTREAM_ERROR = "anysearch_upstream_error"
# 超时
ANYSEARCH_TIMEOUT = "anysearch_timeout"

__all__ = [
    "ANYSEARCH_KEYS_EXHAUSTED",
    "ANYSEARCH_BAD_REQUEST",
    "ANYSEARCH_RATE_LIMITED",
    "ANYSEARCH_UPSTREAM_ERROR",
    "ANYSEARCH_TIMEOUT",
]