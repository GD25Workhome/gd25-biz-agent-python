"""
实验0913-2 确定性运行时：HTTP、HTML 简化、内存库、MCP 工具。

设计要点（沿用 ClaudeTest02 已验证有效的形状）：
  1. 工具只回「简化后的同域链接清单」，【不预分类】——不告诉 Agent 哪条是新闻/翻页
  2. 工具返回值带 pages_remaining / hint，用工具契约引导循环，不靠模型自觉
  3. 超限时工具拒绝执行并给出下一步指令
  4. 每个 run 用全新的 CrawlStore（站间、run 间完全隔离）
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag
from claude_agent_sdk import create_sdk_mcp_server, tool

BASE_DIR = Path(__file__).resolve().parent

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_INTERVAL = 0.4
HTTP_TIMEOUT = 25.0
MAX_PAGES = 8
DATE_RE = re.compile(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})[日]?")


# ---------------------------------------------------------------- 数据结构

@dataclass
class NewsItem:
    """列表页上识别出的一条新闻入口。"""
    url: str
    title: str
    published_at: Optional[str]
    list_page_url: str


@dataclass
class CrawlStore:
    """进程内数据库。每个 run 一份，站间/run 间不共享。"""
    stock_code: str = ""
    company_name: str = ""
    seed_list_url: str = ""
    list_pages: list[dict[str, Any]] = field(default_factory=list)
    news_items: list[NewsItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def news_urls(self) -> list[str]:
        """已记录新闻 URL（去重保序）。"""
        urls: list[str] = []
        seen: set[str] = set()
        for item in self.news_items:
            if item.url not in seen:
                seen.add(item.url)
                urls.append(item.url)
        return urls


def new_store(stock_code: str, company_name: str, seed_list_url: str) -> CrawlStore:
    """为一次独立 run 创建全新的内存库。"""
    return CrawlStore(
        stock_code=stock_code,
        company_name=company_name,
        seed_list_url=seed_list_url,
    )


_LAST_REQUEST_AT = 0.0


# ---------------------------------------------------------------- 工具函数

def _text_result(payload: Any) -> dict[str, Any]:
    """把任意对象包装成 MCP 工具返回。"""
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}]}


def normalize_url(url: str) -> str:
    """
    规范化 URL：小写域名、去 fragment、去多余尾斜杠（保留 query）。

    注意：仅当【没有 query】时才去尾斜杠。
    若 path 尾斜杠 + 有 query，该斜杠是语义的一部分，去掉会把
    `/news/html/?109.html` 变成 `/news/html?109.html`（见 运行说明.md 陷阱 4）。
    """
    parsed = urlparse(url.strip())
    path = parsed.path or "/"
    if not parsed.query and path.endswith("/") and len(path) > 1:
        path = path[:-1]
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", parsed.query, ""))


def _sleep_interval() -> None:
    """遵守最小请求间隔。"""
    global _LAST_REQUEST_AT
    elapsed = time.time() - _LAST_REQUEST_AT
    if elapsed < REQUEST_INTERVAL:
        time.sleep(REQUEST_INTERVAL - elapsed)
    _LAST_REQUEST_AT = time.time()


def fetch_html(url: str) -> tuple[Optional[str], str, int, Optional[str]]:
    """
    同步 GET 网页，跟随重定向。

    Returns:
        (html, 最终 URL, 状态码, 错误信息)
    """
    _sleep_interval()
    try:
        with httpx.Client(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        ) as client:
            response = client.get(url)
            final_url = str(response.url)
            if response.status_code != 200:
                return None, final_url, response.status_code, f"HTTP {response.status_code}"
            return response.text, final_url, response.status_code, None
    except httpx.TimeoutException:
        return None, url, 0, "Timeout"
    except httpx.ConnectError as exc:
        return None, url, 0, f"Connection error: {exc}"
    except Exception as exc:
        return None, url, 0, f"Error: {type(exc).__name__}: {exc}"


def normalize_date(text: str) -> Optional[str]:
    """从文本中抽出 YYYY-MM-DD；抽不到则返回 None。"""
    match = DATE_RE.search(text or "")
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def _link_nearby_text(node: Tag, max_len: int = 200) -> str:
    """取链接自身及父节点文本（用于把日期与标题对上）。"""
    chunks: list[str] = []
    own = node.get_text(" ", strip=True)
    if own:
        chunks.append(own)
    parent = node.parent
    if parent is not None:
        parent_text = parent.get_text(" ", strip=True)
        if parent_text and parent_text != own:
            chunks.append(parent_text)
    return " | ".join(chunks)[:max_len]


def simplify_list_html(html: str, page_url: str) -> str:
    """
    把列表页 HTML 压成同域链接清单，按页面出现顺序输出，【不预分类】。

    Args:
        html: 原始 HTML
        page_url: 当前页最终 URL

    Returns:
        供大模型阅读的纯文本
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    lines: list[str] = []
    seen: set[str] = set()
    page_host = urlparse(page_url).netloc.lower()

    for node in soup.find_all("a"):
        href = (node.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:")) or href == "#":
            continue
        # HTML 实体解码（BeautifulSoup 通常已处理，这里兜底）
        href = (href.replace("&amp;", "&").replace("&#39;", "'")
                    .replace("&quot;", '"').replace("&nbsp;", " "))

        absolute = normalize_url(urljoin(page_url, href))
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc.lower() != page_host:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)

        text = node.get_text(" ", strip=True)
        title_attr = (node.get("otitle") or node.get("title") or "").strip()
        nearby = _link_nearby_text(node)
        date_in_text = normalize_date(nearby) or normalize_date(title_attr)
        display_title = title_attr or text or "(无文本)"
        lines.append(
            f"- href={absolute}\n"
            f"  text={text[:90] or '(空)'}\n"
            f"  title={display_title[:90]}\n"
            f"  nearby={nearby}\n"
            f"  date_in_text={date_in_text or '-'}"
        )

    return "\n".join(
        [
            f"PAGE_URL: {page_url}",
            f"同域链接总数: {len(lines)}（按页面出现顺序，未分类）",
            "",
            "## 链接清单",
            "\n".join(lines) if lines else "（无）",
        ]
    )


def _save_snapshot(snapshot_dir: Path, name: str, html: str) -> None:
    """把原始 HTML 落到 snapshots，便于复盘。"""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / name).write_text(html, encoding="utf-8")


def group_items_by_page(store: CrawlStore) -> OrderedDict[str, list[NewsItem]]:
    """按列表页出现顺序分组新闻条目。"""
    grouped: OrderedDict[str, list[NewsItem]] = OrderedDict()
    for page in store.list_pages:
        key = normalize_url(page.get("final_url") or page.get("requested_url") or "")
        if key and key not in grouped:
            grouped[key] = []
    for item in store.news_items:
        grouped.setdefault(item.list_page_url, []).append(item)
    return grouped


def render_readable_report(store: CrawlStore) -> str:
    """生成给人核对的 Markdown。"""
    grouped = group_items_by_page(store)
    lines: list[str] = [
        f"# {store.company_name} {store.stock_code} 新闻 URL 核对表",
        "",
        f"- 入口页：`{store.seed_list_url}`",
        f"- 最多列表页：{MAX_PAGES}",
        f"- 实际抓到的列表页：{len(store.list_pages)}",
        f"- 新闻 URL 合计（去重）：{len(store.news_urls())}",
        "",
        "> 本实验只采集列表上的新闻入口 URL，未打开详情、未抽取正文。",
        "",
    ]
    for index, (page_url, items) in enumerate(grouped.items(), start=1):
        role = "入口页" if index == 1 else f"第 {index} 页"
        lines += [f"## {role}", "", f"- 列表页 URL：`{page_url}`",
                  f"- 本页新闻数：{len(items)}", ""]
        if not items:
            lines += ["（本页未记录到新闻 URL）", ""]
            continue
        lines += ["| # | 日期 | 标题 | 新闻 URL |", "|---|------|------|----------|"]
        for i, item in enumerate(items, start=1):
            title = (item.title or "(无标题)").replace("|", "\\|")
            lines.append(f"| {i} | {item.published_at or '-'} | {title} | `{item.url}` |")
        lines.append("")

    if store.errors:
        lines += ["## 错误", ""] + [f"- {e}" for e in store.errors] + [""]
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------- MCP 工具工厂

def build_crawl_server(store: CrawlStore, snapshot_dir: Path):
    """
    为一次独立 run 创建 MCP Server。

    注意：store 与 snapshot_dir 通过闭包绑定到本次 run，
    因此不同 run / 不同站之间【不会】共享任何状态。

    Args:
        store: 本次 run 的内存库
        snapshot_dir: 本次 run 的 HTML 快照目录

    Returns:
        SDK MCP Server
    """

    def _pages_remaining() -> int:
        return max(0, MAX_PAGES - len(store.list_pages))

    @tool(
        "fetch_list_page",
        "抓取一个列表页，返回按页面顺序排列的同域链接清单。"
        "不预判哪条是新闻、哪条是翻页。禁止打开新闻详情。",
        {"url": str},
    )
    async def fetch_list_page(args: dict[str, Any]) -> dict[str, Any]:
        """抓取列表页，返回给 Agent 阅读的链接清单。"""
        url = str(args.get("url") or "").strip()
        if not url:
            return _text_result({"ok": False, "error": "url 不能为空"})
        if _pages_remaining() <= 0:
            return _text_result({
                "ok": False,
                "error": f"已达到最大列表页数 {MAX_PAGES}，请调用 save_results",
                "list_pages_fetched": len(store.list_pages),
            })

        html, final_url, status, error = fetch_html(url)
        if error or not html:
            store.errors.append(f"列表页失败 {url}: {error}")
            return _text_result({"ok": False, "url": url, "final_url": final_url, "error": error})

        slug = hashlib.md5(final_url.encode("utf-8")).hexdigest()[:10]
        _save_snapshot(snapshot_dir, f"list_{slug}.html", html)
        store.list_pages.append({
            "requested_url": url,
            "final_url": final_url,
            "http_status": status,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        })
        simplified = simplify_list_html(html, final_url)
        header = (
            f"ok=true\nrequested_url={url}\nfinal_url={final_url}\nhttp_status={status}\n"
            f"list_pages_fetched={len(store.list_pages)}\nmax_pages={MAX_PAGES}\n"
            f"pages_remaining={_pages_remaining()}\n\n"
        )
        return _text_result(header + simplified)

    @tool(
        "record_news_urls",
        "把当前列表页识别出的新闻入口 URL 写入内存库。"
        "items_json 为 JSON 数组，元素含 url，可选 title/published_at；"
        "next_page_url 为后续列表页绝对 URL，没有则传空字符串。不要打开详情页。",
        {"page_url": str, "items_json": str, "next_page_url": str},
    )
    async def record_news_urls(args: dict[str, Any]) -> dict[str, Any]:
        """记录 Agent 从某一页解析出的新闻 URL 与后续列表页。"""
        page_url = normalize_url(str(args.get("page_url") or "").strip())
        next_page_url = str(args.get("next_page_url") or "").strip()
        raw = str(args.get("items_json") or "[]")

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return _text_result({
                "ok": False,
                "error": f"items_json 不是合法 JSON: {exc}",
                "expected": '[{"url":"...","title":"...","published_at":"2026-08-26"}]',
            })
        if not isinstance(parsed, list):
            return _text_result({"ok": False, "error": "items_json 必须是数组"})

        # 本次 fetch 给过的候选 URL 集合（防幻觉：只能从看过的链接里选）
        fetched = set()
        for p in store.list_pages:
            fetched.add(normalize_url(p.get("final_url") or ""))
            fetched.add(normalize_url(p.get("requested_url") or ""))

        added = skipped = 0
        for row in parsed:
            if not isinstance(row, dict):
                skipped += 1
                continue
            href = str(row.get("url") or "").strip()
            if not href:
                skipped += 1
                continue
            abs_url = normalize_url(urljoin(page_url, href))
            title = str(row.get("title") or "").strip()
            published_at = normalize_date(str(row.get("published_at") or "")) or None
            if any(item.url == abs_url for item in store.news_items):
                skipped += 1
                continue
            store.news_items.append(NewsItem(
                url=abs_url, title=title, published_at=published_at, list_page_url=page_url))
            added += 1

        if next_page_url:
            next_page_url = normalize_url(urljoin(page_url, next_page_url))
            for page in store.list_pages:
                if normalize_url(page.get("final_url") or page.get("requested_url") or "") == page_url:
                    page["next_page_url"] = next_page_url
                    break

        return _text_result({
            "ok": True,
            "added": added,
            "skipped": skipped,
            "total_news_urls": len(store.news_items),
            "list_pages_fetched": len(store.list_pages),
            "max_pages": MAX_PAGES,
            "pages_remaining": _pages_remaining(),
            "list_pages_with_items": list(group_items_by_page(store).keys()),
            "next_page_url": next_page_url or None,
            "hint": ("尚未达到最大页数时，请根据当前页内容自行寻找后续列表页并继续 fetch_list_page；"
                     "达到上限或找不到后续列表页则 save_results。"),
        })

    @tool("get_state", "查看当前进度：已抓几个列表页、各页记录了多少新闻 URL。", {})
    async def get_state(args: dict[str, Any]) -> dict[str, Any]:
        """返回抓取进度摘要。"""
        del args
        per_page = {p: len(items) for p, items in group_items_by_page(store).items()}
        return _text_result({
            "seed_list_url": store.seed_list_url,
            "list_pages_fetched": len(store.list_pages),
            "max_pages": MAX_PAGES,
            "pages_remaining": _pages_remaining(),
            "list_page_urls": [p.get("final_url") or p.get("requested_url") for p in store.list_pages],
            "news_url_count": len(store.news_items),
            "per_page_counts": per_page,
            "error_count": len(store.errors),
        })

    @tool("save_results", "把新闻 URL 清单导出为易读 Markdown 和 JSON。完成采集后必须调用。", {})
    async def save_results(args: dict[str, Any]) -> dict[str, Any]:
        """将内存库落盘为 Markdown + JSON。"""
        del args
        out_dir = snapshot_dir.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / "news_urls.md"
        md_path.write_text(render_readable_report(store), encoding="utf-8")

        grouped = group_items_by_page(store)
        payload = {
            "stock_code": store.stock_code,
            "company_name": store.company_name,
            "entry_page": store.seed_list_url,
            "max_pages": MAX_PAGES,
            "list_pages": store.list_pages,
            "pages": [
                {
                    "page_index": index,
                    "is_entry_page": index == 1,
                    "list_page_url": page_url,
                    "news_count": len(items),
                    "news": [
                        {"url": i.url, "title": i.title, "published_at": i.published_at}
                        for i in items
                    ],
                }
                for index, (page_url, items) in enumerate(grouped.items(), start=1)
            ],
            "news_url_count": len(store.news_urls()),
            "errors": store.errors,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
        }
        json_path = out_dir / "news_urls.json"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return _text_result({
            "ok": True,
            "files": [str(md_path), str(json_path)],
            "entry_page": store.seed_list_url,
            "list_pages_fetched": len(store.list_pages),
            "news_url_count": payload["news_url_count"],
        })

    return create_sdk_mcp_server(
        name="crawl",
        version="1.0.0",
        tools=[fetch_list_page, record_news_urls, get_state, save_results],
    )
