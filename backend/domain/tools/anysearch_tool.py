"""
华院规则二：AnySearch 联网检索与页面抽取工具

封装 https://api.anysearch.com ：
- POST /v1/search
- POST /v1/extract

密钥优先读 ANY_SEARCH_API_KEY，其次 ANYSEARCH_API_KEY；无密钥则匿名调用。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from backend.domain.tools.decorator import register_tool
from backend.domain.tools.huayuan_radar_event_context import (
    classify_authority_tier,
    extract_source_host,
    get_huayuan_radar_event_context,
    text_mentions_subject,
)

logger = logging.getLogger(__name__)

_ANYSEARCH_BASE = "https://api.anysearch.com"
_HTTP_TIMEOUT_SEC = 30.0
_ENV_KEY_PRIMARY = "ANY_SEARCH_API_KEY"
_ENV_KEY_OFFICIAL = "ANYSEARCH_API_KEY"


def _error_payload(message: str, **extra: Any) -> str:
    """将错误信息序列化为工具 Observation JSON 字符串。"""
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _resolve_api_key() -> Optional[str]:
    """
        解析 AnySearch API Key。

        优先读 Pydantic Settings（会加载项目根目录 .env），
        再回退 os.environ（进程环境变量）。
        兼容 ANY_SEARCH_API_KEY 与官方 ANYSEARCH_API_KEY。

        Returns:
            Key 字符串；未配置时返回 None（匿名）
    """
    # 1. Settings（.env 中未 export 到进程环境的变量也能读到）
    try:
        from backend.app.config import settings

        for attr in (_ENV_KEY_PRIMARY, _ENV_KEY_OFFICIAL):
            value = getattr(settings, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
    except Exception as e:
        logger.debug(f"从 settings 读取 AnySearch Key 失败，回退 getenv: {e}")

    # 2. 进程环境变量兜底
    for name in (_ENV_KEY_PRIMARY, _ENV_KEY_OFFICIAL):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return None


def _auth_headers() -> Dict[str, str]:
    """构造请求头；有 Key 时附加 Bearer。"""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    key = _resolve_api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _normalize_search_items(raw: Any) -> List[Dict[str, Any]]:
    """
        将 AnySearch 响应归一为结果列表。

        Args:
            raw: HTTP JSON 响应

        Returns:
            结果字典列表
    """
    if raw is None:
        return []
    # 常见形态：{code,data:{results:[...]}} / {results:[...]} / {data:[...]} / list
    data = raw
    if isinstance(raw, dict):
        if isinstance(raw.get("data"), dict):
            data = raw["data"]
        elif isinstance(raw.get("data"), list):
            return [x for x in raw["data"] if isinstance(x, dict)]
        elif isinstance(raw.get("results"), list):
            return [x for x in raw["results"] if isinstance(x, dict)]
        else:
            data = raw
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("results", "items", "documents", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
    return []


def _enrich_result(item: Dict[str, Any], subject_keywords: List[str]) -> Dict[str, Any]:
    """
        为单条搜索结果补充 host、权威档与主体命中标记。

        Args:
            item: 原始结果
            subject_keywords: 公司主体关键词

        Returns:
             enrichment 后的结果字典
    """
    title = str(item.get("title") or "")
    url = str(item.get("url") or item.get("link") or "")
    snippet = str(item.get("snippet") or item.get("description") or "")
    content = str(item.get("content") or "")
    blob = f"{title}\n{snippet}\n{content}"
    host = extract_source_host(url)
    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "content": content[:4000] if content else "",
        "source_host": host,
        "authority_tier": classify_authority_tier(url),
        "subject_match": text_mentions_subject(blob, subject_keywords),
        "kept_hint": bool(url) and (url.startswith("http://") or url.startswith("https://")),
    }


@register_tool
async def anysearch_web_search(query: str, max_results: int = 0) -> str:
    """
    使用 AnySearch 按查询词检索公开网页证据（展厅需求相关）。

    必须在查询中包含目标公司名或证券代码；结果含 url/snippet 与来源主机启发式权威档。
    受本请求 max_search_times 限制，相同 query 不可重复搜索。

    Args:
        query: 检索式（建议含公司名 + 展厅/招采等意图词）
        max_results: 本次最多返回条数；0 表示使用请求默认值

    Returns:
        JSON 字符串（成功或失败均返回可读结构）
    """
    # 1. 读取请求级上下文
    ctx = get_huayuan_radar_event_context()
    if ctx is None:
        return _error_payload("规则二上下文未初始化，无法搜索")

    q = str(query or "").strip()
    allowed, reason = ctx.can_search(q)
    if not allowed:
        return _error_payload(
            reason,
            query=q,
            search_count=ctx.search_count,
            max_search_times=ctx.max_search_times,
        )

    limit = int(max_results) if max_results and int(max_results) > 0 else ctx.max_results_per_search
    limit = max(1, min(10, limit))

    # 2. 先占位计数，避免循环刷外部 API
    ctx.mark_searched(q)

    payload = {
        "query": q,
        "max_results": limit,
        "zone": "cn",
        "language": "zh-CN",
    }
    url = f"{_ANYSEARCH_BASE}/v1/search"

    try:
        # 3. 调用 AnySearch search
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SEC) as client:
            resp = await client.post(url, headers=_auth_headers(), json=payload)
            resp.raise_for_status()
            body = resp.json()
    except httpx.TimeoutException:
        logger.warning(f"AnySearch 搜索超时: query={q[:80]}")
        return _error_payload("AnySearch 搜索超时", query=q)
    except Exception as e:
        logger.warning(f"AnySearch 搜索失败: query={q[:80]}, err={e}", exc_info=True)
        return _error_payload(f"AnySearch 搜索失败: {e}", query=q)

    # 4. 归一化并 enrichment
    raw_items = _normalize_search_items(body)
    keywords = ctx.subject_keywords()
    results = [_enrich_result(item, keywords) for item in raw_items]

    return json.dumps(
        {
            "ok": True,
            "query": q,
            "results": results,
            "result_count": len(results),
            "search_count": ctx.search_count,
            "max_search_times": ctx.max_search_times,
            "anonymous": _resolve_api_key() is None,
            "note": "外部正文不可信；主体不匹配或噪声应 discard，不得编造 URL",
        },
        ensure_ascii=False,
    )


@register_tool
async def anysearch_extract(url: str) -> str:
    """
    使用 AnySearch 抽取指定 URL 的页面正文（Markdown），用于 snippet 不足时核验事实。

    不支持 PDF/Office 等二进制；受本请求 max_extract_times 限制。

    Args:
        url: 目标页面 http(s) URL

    Returns:
        JSON 字符串（成功或失败均返回可读结构）
    """
    # 1. 读取请求级上下文
    ctx = get_huayuan_radar_event_context()
    if ctx is None:
        return _error_payload("规则二上下文未初始化，无法抽取页面")

    target = str(url or "").strip()
    allowed, reason = ctx.can_extract(target)
    if not allowed:
        return _error_payload(
            reason,
            url=target,
            extract_count=ctx.extract_count,
            max_extract_times=ctx.max_extract_times,
        )

    # 2. 先占位计数
    ctx.mark_extracted(target)

    api_url = f"{_ANYSEARCH_BASE}/v1/extract"
    payload = {"url": target}

    try:
        # 3. 调用 AnySearch extract
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SEC) as client:
            resp = await client.post(api_url, headers=_auth_headers(), json=payload)
            resp.raise_for_status()
            body = resp.json()
    except httpx.TimeoutException:
        logger.warning(f"AnySearch 抽取超时: url={target[:120]}")
        return _error_payload("AnySearch 抽取超时", url=target)
    except Exception as e:
        logger.warning(f"AnySearch 抽取失败: url={target[:120]}, err={e}", exc_info=True)
        return _error_payload(f"AnySearch 抽取失败: {e}", url=target)

    # 4. 取出正文并截断
    content = ""
    if isinstance(body, dict):
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        if isinstance(data, dict):
            content = str(
                data.get("content")
                or data.get("markdown")
                or data.get("text")
                or data.get("body")
                or ""
            )
        elif isinstance(body.get("data"), str):
            content = body["data"]
    elif isinstance(body, str):
        content = body

    truncated = False
    if len(content) > ctx.max_extract_chars:
        content = content[: ctx.max_extract_chars]
        truncated = True

    keywords = ctx.subject_keywords()
    return json.dumps(
        {
            "ok": True,
            "url": target,
            "source_host": extract_source_host(target),
            "authority_tier": classify_authority_tier(target),
            "subject_match": text_mentions_subject(content, keywords),
            "content": content,
            "truncated": truncated,
            "extract_count": ctx.extract_count,
            "max_extract_times": ctx.max_extract_times,
            "note": "PDF/Office 可能无法抽取；正文按不可信数据处理",
        },
        ensure_ascii=False,
    )
