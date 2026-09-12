"""
巨潮全文检索适配器（画像证据采集用）。

策略（U3 默认）：用公司名作 searchkey，结果按 secCode 过滤到目标公司。
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Optional

import requests

log = logging.getLogger("radar.cninfo")

SEARCH_URL = "http://www.cninfo.com.cn/new/fulltextSearch/full"
STATIC_PDF_BASE = "https://static.cninfo.com.cn/"

# 绕过系统代理，避免本机代理导致外网失败
os.environ.setdefault("NO_PROXY", "*")
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)

_session = requests.Session()
_session.trust_env = False
_session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "http://www.cninfo.com.cn/",
    }
)


def _zfill_code(code: Optional[str]) -> str:
    if not code:
        return ""
    return str(code).strip().zfill(6)


def search_announcements(
    keyword: str,
    *,
    sdate: str,
    edate: str,
    page_size: int = 30,
    max_pages: int = 3,
    interval_sec: float = 1.0,
) -> list[dict[str, Any]]:
    """按关键词分页检索巨潮公告。"""
    results: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        try:
            resp = _session.get(
                SEARCH_URL,
                params={
                    "searchkey": keyword,
                    "sdate": sdate,
                    "edate": edate,
                    "pageNum": page,
                    "pageSize": page_size,
                    "isTitleSearch": "false",
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.warning("巨潮检索失败 keyword=%s page=%s err=%s", keyword, page, exc)
            break

        announcements = data.get("announcements") or []
        if not announcements:
            break
        results.extend(announcements)
        total_pages = int(data.get("totalpages") or 1)
        if page >= total_pages:
            break
        time.sleep(interval_sec)
    return results


def filter_by_stock_code(items: list[dict[str, Any]], stock_code: str) -> list[dict[str, Any]]:
    """用证券代码过滤公告列表。"""
    target = _zfill_code(stock_code)
    if not target:
        return []
    matched = []
    for item in items:
        code = _zfill_code(item.get("secCode"))
        if code == target:
            matched.append(item)
    return matched


def build_pdf_url(adjunct_url: Optional[str]) -> Optional[str]:
    if not adjunct_url:
        return None
    if adjunct_url.startswith("http"):
        return adjunct_url
    return STATIC_PDF_BASE + adjunct_url.lstrip("/")


def parse_announcement_time(value: Any) -> Optional[datetime]:
    """解析巨潮时间：可能是毫秒时间戳或字符串。"""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e12:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts)
        text = str(value).strip()
        if text.isdigit():
            ts = float(text)
            if ts > 1e12:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:19], fmt)
            except ValueError:
                continue
    except Exception:
        return None
    return None


def download_and_extract_text(
    pdf_url: str,
    *,
    max_chars: int,
    max_pages: int = 80,
) -> tuple[Optional[str], Optional[str]]:
    """
    下载 PDF 并抽取文本。

    Args:
        pdf_url: PDF 地址（通常 static.cninfo.com.cn）
        max_chars: 正文最大字符数，超出截断
        max_pages: 最多解析页数

    Returns:
        (text, error)：成功时 error 为 None；失败时 text 为 None
    """
    try:
        resp = _session.get(pdf_url, timeout=90)
        resp.raise_for_status()
        raw = resp.content or b""
        if not raw.startswith(b"%PDF"):
            magic = raw[:8]
            return None, f"not_pdf magic={magic!r}"

        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(raw))
        page_count = len(reader.pages)
        limit = max(1, max_pages)
        parts: list[str] = []
        for idx, page in enumerate(reader.pages):
            if idx >= limit:
                log.info(
                    "PDF 页数超限 url=%s pages=%s limit=%s，已截断抽取",
                    pdf_url[:120],
                    page_count,
                    limit,
                )
                break
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
        if not text:
            return None, "pdf_text_empty(可能是扫描件需OCR)"
        if len(text) > max_chars:
            text = text[:max_chars]
        return text, None
    except Exception as exc:
        return None, str(exc)[:200]


def make_summary(raw: Optional[str], fallback_title: str, max_chars: int) -> str:
    """生成 content_summary：优先命中片段，否则标题截断。"""
    text = (raw or "").strip()
    if not text:
        text = fallback_title or ""
    # 去掉简单 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    text = " ".join(text.split())
    if len(text) > max_chars:
        return text[:max_chars]
    return text
