"""
URL 规范化 —— 新闻 URL 去重键。

⚠️ 本模块规则必须与 exhibition 侧
`RadarUrlNormUtil.normalize()` 逐字一致，否则：
  1. 调用方传入的 known_urls 在本侧认不出，L1 短路失效（白花钱）
  2. 落库时同一 URL 会存成两条

规则（两条反直觉细节均来自实验中的真实 bug，见
company_claude_cral/实验0913-2/运行说明.md 陷阱 4）：
  1. 仅保留 host + path + query（去 scheme、去 fragment）
  2. host 小写
  3. 【仅当没有 query 时】才去 path 尾斜杠
     若 path 尾斜杠 + 有 query，该斜杠是语义的一部分：
     去掉会把 `/news/html/?109.html` 变成 `/news/html?109.html`，
     导致华岭股份 24 条真实 URL 全部匹配失败。
  4. query 参数按键名排序，保证 `?a=1&b=2` 与 `?b=2&a=1` 归一

设计文档：华院Agent设计/260914-整体重构/02-gd25侧详细设计.md §5.1
"""
from __future__ import annotations

from urllib.parse import urlparse

__all__ = ["normalize", "normalize_many"]


def normalize(url: str) -> str:
    """
    把 URL 归一化为去重键。

    Args:
        url: 原始 URL

    Returns:
        归一化字符串，形如 `host/path?query`；解析失败时回退为原文 strip 结果。

    Examples:
        >>> normalize("https://Example.com/a/?x=1#frag")
        'example.com/a?x=1'
        >>> normalize("https://example.com/news/html/?109.html")
        'example.com/news/html/?109.html'
        >>> normalize("https://example.com/a?b=2&a=1")
        'example.com/a?a=1&b=2'
    """
    raw = (url or "").strip()
    if not raw:
        return ""

    try:
        parsed = urlparse(raw)
        if not parsed.netloc:
            # 非绝对 URL（无 host），无法归一，回退原文
            return raw

        host = parsed.netloc.lower()
        path = parsed.path or "/"
        query = parsed.query

        # 规则 3：仅当没有 query 时才去尾斜杠
        if not query and path.endswith("/") and len(path) > 1:
            path = path[:-1]

        norm_query = _normalize_query(query)
        return f"{host}{path}?{norm_query}" if norm_query else f"{host}{path}"
    except Exception:
        # 与 Java 侧一致：解析失败回退原文
        return raw


def _normalize_query(query: str) -> str:
    """
    按参数排序后重组 query。

    ⚠️ 不能用 parse_qsl + urlencode 直接往返：部分站点把 query 当路径用
    （如华岭的 `/news/html/?109.html`，query 是 `109.html`，本就没有 `=`）。
    urlencode 会给它补一个 `=`，变成 `109.html=` —— 与 Java 侧的
    「整串按 `&` 切分后自然排序」不一致，直接破坏去重键。

    因此这里只按 `&` 切分、对每个片段做自然排序，不解析键值对。
    这与 Java 侧 `StrUtil.split(query,'&')` + `pairs.sort()` 语义一致。
    """
    if not query:
        return ""
    segments = [s for s in query.split("&") if s != ""]
    if not segments:
        return query
    segments.sort()
    return "&".join(segments)


def normalize_many(urls: list[str]) -> set[str]:
    """
    批量归一化为集合，便于 O(1) 命中判断。

    Args:
        urls: 原始 URL 列表

    Returns:
        归一化后的集合（已去空串）
    """
    out: set[str] = set()
    for u in urls or []:
        norm = normalize(u)
        if norm:
            out.add(norm)
    return out
