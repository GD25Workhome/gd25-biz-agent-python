"""证据来源抑制表（D7）。

**故意保持窄**：只抑制"行情 / 指数 / 列表 / 聚合"这类**没有正文事实**的页面，
不抑制问答、公告、官网等可能承载事实的来源（例：`ir.p5w.net/question/...` 是
带公司答复的互动记录，历史上被正确用作证据，**不在此表**）。

无日期/无正文的判定另有两条路：`validity.is_run_date_stamp`（跑批日戳）与
后续"正文交叉核验"（需图内节点）。

设计：``华院Agent设计/03-决策记录/261020-06-时效审查节点与证据日期纪律.md`` §3.1（D7）
"""
from __future__ import annotations

from typing import Tuple
from urllib.parse import urlparse

# host 前缀/包含片段 → 明确是行情或指数行情页（**收窄**：不再用宽 host 片段，避免误伤公告/新闻）
_PREFIX_HOSTS = ("quote.", "hq.", "stockpage.", "basic.", "profile.")
_CONTAIN_HOSTS = (
    "stcn.com/quotes",  # 证券时报行情/投关模板页（5333 的 e4 落在这里）
    "eastmoney.com/quote",
    "sina.com.cn/realstock",
    "xueqiu.com/S/",  # 雪球个股页
)

# URL 路径片段 → 行情/报价/列表页
_PATH_FRAGMENTS = (
    "/quotes/",
    "/realstock/",
    "/hq/",
    "/hangqing/",
)

# 明确豁免：公告 / 新闻 / 交易所披露 —— 这些是**有正文事实**的来源，绝不抑制
_EXEMPT_HOST_PREFIXES = ("notice.", "news.", "static.cninfo", "money.finance.sina.com.cn")
_EXEMPT_PATH_FRAGMENTS = ("/corp/view/", "/finalpage/", "/api/pdf/")


def suppressed_reason(url) -> str:
    """
        判断 URL 是否命中来源抑制表。

        先过**豁免**（公告 / 新闻 / 交易所披露），再判行情/列表页 —— 防"公告 PDF 被当行情页剔掉"。

        Args:
            url: 证据 URL

        Returns:
            命中的原因文案；未命中或命中豁免返回空串
    """
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    except ValueError:
        return ""
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    full = f"{host}{path}"

    # 1. 豁免优先：公告 / 新闻 / 交易所披露
    if any(host.startswith(prefix) for prefix in _EXEMPT_HOST_PREFIXES):
        return ""
    if any(fragment in path for fragment in _EXEMPT_PATH_FRAGMENTS):
        return ""

    # 2. 行情 / 指数 / 列表页
    for prefix in _PREFIX_HOSTS:
        if host.startswith(prefix):
            return f"行情/指数页（host 前缀 {prefix}）"
    for fragment in _CONTAIN_HOSTS:
        if fragment in full:
            return f"行情/聚合页（命中 {fragment}）"
    for fragment in _PATH_FRAGMENTS:
        if fragment in path:
            return f"行情/报价列表页（路径 {fragment}）"
    return ""


def is_suppressed_url(url) -> Tuple[bool, str]:
    """
        URL 是否应被作为证据剔除。

        Args:
            url: 证据 URL

        Returns:
            (是否剔除, 原因)
    """
    reason = suppressed_reason(url)
    return (bool(reason), reason)