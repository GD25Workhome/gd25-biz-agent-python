"""
巨潮全文检索适配器（画像证据采集用）。

策略（U3 默认）：用公司名作 searchkey，结果按 secCode 过滤到目标公司。

限速（检索 + PDF 共用）：
- 基准间隔 ``RADAR_CNINFO_REQUEST_INTERVAL_SEC``（默认 5s）
- 再加随机抖动 ``[0, RADAR_CNINFO_REQUEST_JITTER_SEC]``（默认 4s）
- 实际相邻请求间隔约 5～9 秒
- 进程内 ``threading.Lock`` 串行化：限速状态 + Session 调用，避免 discover/content
  双线程并发打同一 Session
"""

from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
from datetime import datetime
from typing import Any, Optional

from curl_cffi import requests

log = logging.getLogger("radar.cninfo")

SEARCH_URL = "http://www.cninfo.com.cn/new/fulltextSearch/full"
STATIC_PDF_BASE = "https://static.cninfo.com.cn/"

# 2026-09-16 实证：static.cninfo.com.cn 的 WAF 按 TLS 指纹(JA3/JA4)拦截
# 非浏览器 HTTPS 客户端（requests/curl 同机同出口 IP 均 403），并非 IP 封禁；
# 改用 curl_cffi 仿真 Chrome 指纹后同机可正常下载（详见
# ai_docs/26091608-巨潮PDF下载403问题小结.md）。
# curl_cffi 的 Session API 与 requests 兼容，接口层无感。
#
# L2 前置：禁止在 import 时改 os.environ（NO_PROXY / pop 代理）——会静默破坏
# 同进程 backend 的 LLM/embedding 出网。绕过代理仅对本 Session：trust_env=False。
_session = requests.Session(impersonate="chrome", trust_env=False)
_session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "http://www.cninfo.com.cn/",
    }
)

# 进程级串行：限速计数 + HTTP Session（discover / content 可能同进程双线程）
_http_lock = threading.Lock()
_last_request_mono: float = 0.0
_base_interval_sec: float = float(
    os.getenv("RADAR_CNINFO_REQUEST_INTERVAL_SEC", "5") or "5"
)
_jitter_sec: float = float(os.getenv("RADAR_CNINFO_REQUEST_JITTER_SEC", "4") or "4")


def configure_request_pace(
    base_interval_sec: float = 5.0,
    jitter_sec: float = 4.0,
) -> None:
    """
    运行时覆盖巨潮请求节奏（线程安全）。

    Args:
        base_interval_sec: 基准间隔秒，默认 5
        jitter_sec: 随机追加上限秒，实际等待 = base + U(0, jitter)
    """
    global _base_interval_sec, _jitter_sec
    with _http_lock:
        _base_interval_sec = max(0.0, float(base_interval_sec))
        _jitter_sec = max(0.0, float(jitter_sec))
    log.info(
        "巨潮请求节奏已配置 base=%.2fs jitter=0~%.2fs（目标间隔约 %.0f～%.0fs）",
        _base_interval_sec,
        _jitter_sec,
        _base_interval_sec,
        _base_interval_sec + _jitter_sec,
    )


def _pace_wait_locked() -> None:
    """
    在已持有 ``_http_lock`` 的前提下等待下一次请求窗口。

    持锁 sleep：保证全局单飞，避免双线程同时越过间隔去打 Session。
    """
    global _last_request_mono
    interval = _base_interval_sec
    if _jitter_sec > 0:
        interval += random.uniform(0.0, _jitter_sec)
    now = time.monotonic()
    if _last_request_mono > 0:
        wait = (_last_request_mono + interval) - now
        if wait > 0:
            log.debug(
                "巨潮限速等待 %.2fs（本次目标间隔 %.2fs）",
                wait,
                interval,
            )
            time.sleep(wait)
    _last_request_mono = time.monotonic()


def _http_get(url: str, *, timeout: float, params: Optional[dict] = None):
    """
    线程安全的巨潮 GET：先限速再走模块级 Session。

    锁覆盖「等待 + 请求」，Session 不会被多线程并发使用。
    """
    with _http_lock:
        _pace_wait_locked()
        return _session.get(url, params=params, timeout=timeout)


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
    interval_sec: float = 0.0,
) -> list[dict[str, Any]]:
    """
    按关键词分页检索巨潮公告。

    Args:
        interval_sec: 已废弃。页间间隔改由模块级 ``configure_request_pace`` /
            ``RADAR_CNINFO_REQUEST_*`` 统一控制；保留参数仅为兼容旧调用方。
    """
    del interval_sec  # 兼容旧签名，实际节奏见 _http_get
    results: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        try:
            resp = _http_get(
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
        # HTTP 在锁内完成；PDF 解析在锁外，避免抽字阻塞检索/其它下载排队
        resp = _http_get(pdf_url, timeout=90)
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
