"""
新闻抓取 MCP 工具与会话状态。

移植自 company_claude_cral/实验0913-2/crawl_runtime.py，生产化改造：
  1. 同步 httpx.Client → 异步 httpx.AsyncClient（不阻塞事件循环）
  2. 结果不再落盘，改为纯内存返回
  3. 新增 known_urls：提示词命中信号 + 返回前过滤（去掉已知 URL）
  4. 新增反幻觉校验：只能记录 fetch_list_page 返回过的候选

设计要点（沿用实验已验证有效的形状，勿改）：
  - 工具只回「简化后的同域链接清单」，【不预分类】——
    不告诉 Agent 哪条是新闻、哪条是翻页。预分类会让 Agent 退化成规则执行者。
  - 工具返回值带 pages_remaining / hint，用工具契约引导循环，不靠模型自觉。
  - 超限时工具拒绝执行并给出下一步指令。

设计文档：华院Agent设计/260914-整体重构/02-gd25侧详细设计.md §4.2
"""
from __future__ import annotations

import asyncio
import json
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag
from claude_agent_sdk import create_sdk_mcp_server, tool

from backend.domain.news_crawl.url_norm import normalize

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT = 25.0
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
    """
    本次抓取的内存库。每次请求一份，请求间零共享。"""

    company_name: str = ""
    stock_code: str = ""
    seed_url: str = ""
    max_pages: int = 3
    known_norm: set[str] = field(default_factory=set)
    list_pages: list[dict[str, Any]] = field(default_factory=list)
    news_items: list[NewsItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # 每次 fetch_list_page 返回过的候选 URL（反幻觉校验用）
    fetched_candidates: set[str] = field(default_factory=set)
    # 命中 known_urls 的累计条数
    known_hit_count: int = 0
    # 命中 known_urls 后置位，命令式硬停：后续 fetch_list_page 一律拒绝
    pagination_stopped: bool = False

    def news_urls(self, exclude_known: bool = True) -> list[str]:
        """
        已记录新闻 URL（去重保序）。

        Args:
            exclude_known: 是否排除 known_urls 命中的条目（L2 过滤）
        """
        urls: list[str] = []
        seen: set[str] = set()
        for item in self.news_items:
            norm = normalize(item.url)
            if norm in seen:
                continue
            if exclude_known and norm in self.known_norm:
                continue
            seen.add(norm)
            urls.append(item.url)
        return urls

    def new_items(self) -> list[NewsItem]:
        """返回 known_urls 之外的条目（去重保序）。"""
        out: list[NewsItem] = []
        seen: set[str] = set()
        for item in self.news_items:
            norm = normalize(item.url)
            if norm in seen or norm in self.known_norm:
                continue
            seen.add(norm)
            out.append(item)
        return out


# ---------------------------------------------------------------- 工具函数

def _text_result(payload: Any) -> dict[str, Any]:
    """把任意对象包装成 MCP 工具返回。"""
    text = payload if isinstance(payload, str) else json.dumps(
        payload, ensure_ascii=False, indent=2
    )
    return {"content": [{"type": "text", "text": text}]}


def normalize_url(url: str) -> str:
    """
    轻量 URL 规整：去 fragment、小写域名。

    ⚠️ 与 url_norm.normalize 不同 —— 这里【保留 scheme 与尾斜杠】，
    因为要作为真实请求 URL 使用。仅当无 query 时才去尾斜杠，
    与 judge 侧保持一致（见 运行说明.md 陷阱 4）。
    """
    parsed = urlparse((url or "").strip())
    path = parsed.path or "/"
    if not parsed.query and path.endswith("/") and len(path) > 1:
        path = path[:-1]
    return urlunparse(
        (parsed.scheme, parsed.netloc.lower(), path, "", parsed.query, "")
    )


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
        href = (
            href.replace("&amp;", "&").replace("&#39;", "'")
            .replace("&quot;", '"').replace("&nbsp;", " ")
        )

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

    return "\n".join([
        f"PAGE_URL: {page_url}",
        f"同域链接总数: {len(lines)}（按页面出现顺序，未分类）",
        "",
        "## 链接清单",
        "\n".join(lines) if lines else "（无）",
    ])


def group_items_by_page(store: CrawlStore) -> "OrderedDict[str, list[NewsItem]]":
    """按列表页出现顺序分组新闻条目。"""
    grouped: OrderedDict[str, list[NewsItem]] = OrderedDict()
    for page in store.list_pages:
        key = normalize_url(page.get("final_url") or page.get("requested_url") or "")
        if key and key not in grouped:
            grouped[key] = []
    for item in store.news_items:
        grouped.setdefault(item.list_page_url, []).append(item)
    return grouped


# ---------------------------------------------------------------- MCP 工具工厂

def build_crawl_server(store: CrawlStore, request_interval: float = 0.4):
    """
    为一次抓取请求创建 MCP Server。

    store 通过闭包绑定，因此不同请求之间【不会】共享任何状态。

    Args:
        store: 本次请求的内存库
        request_interval: 同站最小请求间隔（秒），礼貌爬取

    Returns:
        SDK MCP Server
    """

    _last_request_at = 0.0
    _lock = asyncio.Lock()

    async def _fetch_html(url: str) -> tuple[Optional[str], str, int, Optional[str]]:
        """
        异步 GET 网页，跟随重定向，遵守最小请求间隔。

        Returns:
            (html, 最终 URL, 状态码, 错误信息)
        """
        nonlocal _last_request_at
        async with _lock:
            loop = asyncio.get_running_loop()
            elapsed = loop.time() - _last_request_at
            if elapsed < request_interval:
                await asyncio.sleep(request_interval - elapsed)
            _last_request_at = loop.time()

        try:
            async with httpx.AsyncClient(
                timeout=HTTP_TIMEOUT,
                follow_redirects=True,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            ) as client:
                response = await client.get(url)
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

    def _pages_remaining() -> int:
        return max(0, store.max_pages - len(store.list_pages))

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
        # 已命中已知 URL → 命令式硬停，不再允许翻页
        if store.pagination_stopped:
            return _text_result({
                "ok": False,
                "error": (
                    "已出现调用方提供的已知新闻 URL，禁止继续翻页。"
                    "请立即调用 save_results 提交结果。"
                ),
                "list_pages_fetched": len(store.list_pages),
                "known_hit_count": store.known_hit_count,
            })
        if _pages_remaining() <= 0:
            return _text_result({
                "ok": False,
                "error": f"已达到最大列表页数 {store.max_pages}，请调用 save_results",
                "list_pages_fetched": len(store.list_pages),
            })

        html, final_url, status, error = await _fetch_html(url)
        if error or not html:
            store.errors.append(f"列表页失败 {url}: {error}")
            return _text_result({
                "ok": False, "url": url, "final_url": final_url, "error": error,
            })

        store.list_pages.append({
            "requested_url": url,
            "final_url": final_url,
            "http_status": status,
        })
        simplified = simplify_list_html(html, final_url)

        # 记录本页候选 URL，供 record_news_urls 做反幻觉校验；
        # 同时检测候选是否命中 known_urls —— 命中即置位硬停。
        # 注意口径：候选存的是 normalize_url（保留 scheme），
        # 与 known_norm 比较必须再过一遍 url_norm.normalize。
        known_on_page = 0
        store.fetched_candidates.add(normalize_url(final_url))
        store.fetched_candidates.add(normalize_url(url))
        for line in simplified.splitlines():
            line = line.strip()
            if line.startswith("- href="):
                candidate = normalize_url(line[len("- href="):])
                store.fetched_candidates.add(candidate)
                if normalize(candidate) in store.known_norm:
                    known_on_page += 1
        if known_on_page > 0:
            store.pagination_stopped = True

        header = (
            f"ok=true\nrequested_url={url}\nfinal_url={final_url}\nhttp_status={status}\n"
            f"list_pages_fetched={len(store.list_pages)}\nmax_pages={store.max_pages}\n"
            f"pages_remaining={_pages_remaining()}\n"
            f"known_hit_on_page={known_on_page}\n\n"
        )
        if store.pagination_stopped:
            header += (
                "本页已出现调用方提供的已知新闻 URL，已到历史区域。\n"
                "禁止继续翻页：记录完本页的新 URL 后立即调用 save_results。\n\n"
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
        # ⚠️ 相对链接必须对【原始 page_url】做 urljoin，不能对 normalize_url 之后的。
        # normalize_url 会去掉尾斜杠（列表页 `/news/` → `/news`），
        # 再 urljoin 就会把 `1.html` 解析到上一层 `/1.html`，
        # 于是每条相对链接都会被反幻觉校验判成"编造"而整批拒绝。
        raw_page_url = str(args.get("page_url") or "").strip()
        page_url = normalize_url(raw_page_url)
        next_page_url = str(args.get("next_page_url") or "").strip()
        raw = str(args.get("items_json") or "[]")

        def _abs(href: str) -> str:
            """把可能是相对路径的 href 解析为绝对 URL 并归一。"""
            return normalize_url(urljoin(raw_page_url or page_url, href))

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
        if not parsed:
            # ⚠️ 空数组必须判失败：Agent 常在「本页确实没有新条目」时传 []，
            # 但更多是自己把参数名写错（如传成 items 而非 items_json），
            # 那会静默通过并让 Agent 以为「记录成功、可以收工」，
            # 最终返回空结果却不报错 —— 比报错更难排查。
            return _text_result({
                "ok": False,
                "error": "items_json 为空数组，未记录任何条目",
                "expected": (
                    '参数名为 items_json，值是【JSON 字符串】而非数组本身，'
                    '例如 "items_json": "[{\\"url\\":\\"http://...\\"}]"'
                ),
                "hint": (
                    "本页若无新增新闻，请明确调用 save_results 结束，"
                    "不要用空数组反复试探。"
                ),
            })

        # 反幻觉校验：只能记录 fetch_list_page 返回过的候选
        unknown: list[str] = []
        rows: list[dict[str, Any]] = []
        for row in parsed:
            if not isinstance(row, dict):
                continue
            href = str(row.get("url") or "").strip()
            if not href:
                continue
            abs_url = _abs(href)
            if abs_url not in store.fetched_candidates:
                unknown.append(abs_url)
                continue
            rows.append({"abs_url": abs_url, "row": row})

        if unknown:
            return _text_result({
                "ok": False,
                "error": f"{len(unknown)} 条 URL 未出现在任何已抓取列表页上",
                "unknown_sample": unknown[:3],
                "hint": "只能记录 fetch_list_page 返回过的链接，不要凭路径猜测。",
            })

        added = 0
        hit_this_page = 0
        for item in rows:
            abs_url = item["abs_url"]
            row = item["row"]
            if any(normalize(i.url) == normalize(abs_url) for i in store.news_items):
                continue
            title = str(row.get("title") or "").strip()
            published_at = normalize_date(str(row.get("published_at") or "")) or None
            store.news_items.append(NewsItem(
                url=abs_url, title=title,
                published_at=published_at, list_page_url=page_url,
            ))
            added += 1
            if normalize(abs_url) in store.known_norm:
                hit_this_page += 1

        store.known_hit_count += hit_this_page

        if next_page_url:
            next_page_url = _abs(next_page_url)
            for page in store.list_pages:
                if normalize_url(
                    page.get("final_url") or page.get("requested_url") or ""
                ) == page_url:
                    page["next_page_url"] = next_page_url
                    break

        return _text_result({
            "ok": True,
            "added": added,
            "total_news_urls": len(store.news_items),
            "new_urls_not_known": len(store.news_urls(exclude_known=True)),
            "known_hit_count": hit_this_page,
            "list_pages_fetched": len(store.list_pages),
            "max_pages": store.max_pages,
            "pages_remaining": _pages_remaining(),
            "next_page_url": next_page_url or None,
            "hint": _build_hint(hit_this_page),
        })

    @tool("get_state", "查看当前进度：已抓几个列表页、各页记录了多少新闻 URL。", {})
    async def get_state(args: dict[str, Any]) -> dict[str, Any]:
        """返回抓取进度摘要。"""
        del args
        per_page = {
            p: len(items) for p, items in group_items_by_page(store).items()
        }
        return _text_result({
            "seed_list_url": store.seed_url,
            "list_pages_fetched": len(store.list_pages),
            "max_pages": store.max_pages,
            "pages_remaining": _pages_remaining(),
            "list_page_urls": [
                p.get("final_url") or p.get("requested_url") for p in store.list_pages
            ],
            "news_url_count": len(store.news_items),
            "new_urls_not_known": len(store.news_urls(exclude_known=True)),
            "known_urls_provided": len(store.known_norm),
            "known_hit_count": store.known_hit_count,
            "pagination_stopped": store.pagination_stopped,
            "per_page_counts": per_page,
            "error_count": len(store.errors),
        })

    @tool("save_results", "把新闻 URL 清单提交为最终结果。完成采集后必须调用。", {})
    async def save_results(args: dict[str, Any]) -> dict[str, Any]:
        """提交最终结果（纯内存，不落盘）。"""
        del args
        new_items = store.new_items()
        return _text_result({
            "ok": True,
            "submitted": True,
            "entry_page": store.seed_url,
            "list_pages_fetched": len(store.list_pages),
            "total_news_urls": len(store.news_items),
            "new_urls_not_known": len(new_items),
            "known_hit_count": store.known_hit_count,
            "pagination_stopped": store.pagination_stopped,
            "note": "结果已提交，可以结束。",
        })

    return create_sdk_mcp_server(
        name="crawl",
        version="1.0.0",
        tools=[fetch_list_page, record_news_urls, get_state, save_results],
    )


def _build_hint(hit_known: int) -> str:
    """
    按命中情况给出下一步指令。

    ⚠️ 命中即命令式硬停（与 fetch_list_page 侧的 pagination_stopped 一致）：
    禁止继续翻页，记录完本页新 URL 后立即 save_results。
    """
    if hit_known > 0:
        return (
            f"本页有 {hit_known} 条命中调用方提供的已知新闻 URL，已到历史区域。"
            "禁止继续翻页：记录完本页的新 URL 后立即调用 save_results。"
        )
    return (
        "尚未达到最大页数时，请根据当前页内容自行寻找后续列表页并继续 "
        "fetch_list_page；达到上限或找不到后续列表页则 save_results。"
    )
