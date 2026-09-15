"""
MCP 工具契约单测（不打网络）。

工具签名里的 items_json 是【JSON 字符串】而非数组，Agent 很容易传错；
传错时若静默返回 ok=true，Agent 会以为记录成功而收工，最终结果为空却不报错。
本文件锁住这些「不能沉默」的边界。

设计文档：华院Agent设计/260914-整体重构/02-gd25侧详细设计.md §4.2
"""
import asyncio
import json

import pytest
from claude_agent_sdk import SdkMcpTool, ToolAnnotations

import backend.domain.news_crawl.crawl_tools as ct
from backend.domain.news_crawl.crawl_tools import (
    CrawlStore,
    normalize_date,
    normalize_url,
    simplify_list_html,
)
from backend.domain.news_crawl.url_norm import normalize_many


@pytest.fixture
def tools(monkeypatch):
    """
    拦截 @tool 装饰器，直接把四个工具的 handler 拿出来单测。

    这样既能验工具契约，又不必启动 Agent 或起 MCP server。
    """
    captured: dict = {}

    def fake_tool(name, desc, schema):
        def deco(fn):
            captured[name] = fn
            return SdkMcpTool(name=name, description=desc, input_schema=schema,
                              handler=fn, annotations=ToolAnnotations())
        return deco

    monkeypatch.setattr(ct, "tool", fake_tool)
    store = CrawlStore(seed_url="http://s.com/news", max_pages=3)
    ct.build_crawl_server(store, request_interval=0.0)
    return captured, store


def _call(fn, args):
    """调用工具并解析其 JSON 文本返回。"""
    result = asyncio.run(fn(args))
    return json.loads(result["content"][0]["text"])


def _seed_candidate(store, url="http://s.com/news/1.html"):
    """模拟 fetch_list_page 已经返回过这个候选。"""
    store.fetched_candidates.add(url)
    return url


class TestRecordRejectsBadInput:
    def test_empty_array_is_rejected(self, tools):
        """
        ⚠️ 回归测试：空数组必须判失败。

        原先传 [] 会返回 ok=true / added=0 —— Agent 把参数名写成 items
        而非 items_json 时正是这个结果，它会以为「记录成功、可以收工」，
        最终产出空列表却不报错。
        """
        captured, _ = tools
        out = _call(captured["record_news_urls"],
                    {"page_url": "", "items_json": "[]", "next_page_url": ""})
        assert out["ok"] is False
        assert "空数组" in out["error"]
        assert "items_json" in out["expected"]

    def test_invalid_json_is_rejected(self, tools):
        captured, _ = tools
        out = _call(captured["record_news_urls"],
                    {"page_url": "", "items_json": "{不是数组", "next_page_url": ""})
        assert out["ok"] is False
        assert "JSON" in out["error"]

    def test_non_array_json_is_rejected(self, tools):
        captured, _ = tools
        out = _call(captured["record_news_urls"],
                    {"page_url": "", "items_json": '{"url":"http://s.com/1"}',
                     "next_page_url": ""})
        assert out["ok"] is False
        assert "数组" in out["error"]


class TestAntiHallucination:
    def test_fabricated_url_is_rejected(self, tools):
        """没在列表页出现过的 URL 一律不认 —— 防 Agent 凭路径规律编造。"""
        captured, _ = tools
        out = _call(captured["record_news_urls"],
                    {"page_url": "", "items_json": json.dumps([
                        {"url": "http://s.com/news/999999.html", "title": "编造"}]),
                     "next_page_url": ""})
        assert out["ok"] is False
        assert "未出现在" in out["error"]

    def test_accepted_candidate_is_recorded(self, tools):
        captured, store = tools
        url = _seed_candidate(store)
        out = _call(captured["record_news_urls"],
                    {"page_url": "http://s.com/news", "items_json": json.dumps([
                        {"url": url, "title": "标题", "published_at": "2026-08-26"}]),
                     "next_page_url": ""})
        assert out["ok"] is True and out["added"] == 1
        assert len(store.news_items) == 1
        assert store.news_items[0].published_at == "2026-08-26"

    def test_one_bad_url_rejects_whole_batch(self, tools):
        """一批里混了编造的 URL，整批拒绝 —— 不给「部分成功」留模糊地带。"""
        captured, store = tools
        good = _seed_candidate(store)
        out = _call(captured["record_news_urls"],
                    {"page_url": "", "items_json": json.dumps([
                        {"url": good}, {"url": "http://evil.com/fake"}]),
                     "next_page_url": ""})
        assert out["ok"] is False
        assert store.news_items == []

    def test_relative_url_resolved_against_page_url(self, tools):
        """
        Agent 给相对路径时按 page_url 补全后再校验。

        ⚠️ 必须对【原始 page_url】做 urljoin，不能对 normalize_url 之后的。
        normalize_url 会去掉尾斜杠（`/news/` → `/news`），再 urljoin 就会把
        `1.html` 解析到上一层 `/1.html`，导致每条相对链接都被判成"编造"而整批拒绝。
        """
        captured, store = tools
        _seed_candidate(store, "http://s.com/news/1.html")
        out = _call(captured["record_news_urls"],
                    {"page_url": "http://s.com/news/",
                     "items_json": json.dumps([{"url": "1.html"}]), "next_page_url": ""})
        assert out["ok"] is True and out["added"] == 1

    def test_nested_relative_path_resolved_correctly(self, tools):
        """深层相对路径同样要对原始 page_url 解析（回归：曾解析到上一层）。"""
        captured, store = tools
        _seed_candidate(store, "http://s.com/news/2026/1.html")
        out = _call(captured["record_news_urls"],
                    {"page_url": "http://s.com/news/list/",
                     "items_json": json.dumps([{"url": "../2026/1.html"}]),
                     "next_page_url": ""})
        assert out["ok"] is True, out

    def test_relative_next_page_url_resolved_correctly(self, tools):
        """next_page_url 走同一个解析路径，也要对原始 page_url 解析。"""
        captured, store = tools
        store.list_pages = [{"final_url": "http://s.com/news"}]
        out = _call(captured["record_news_urls"],
                    {"page_url": "http://s.com/news/",
                     "items_json": json.dumps([{"url": _seed_candidate(store)}]),
                     "next_page_url": "index_2.html"})
        assert out["ok"] is True
        assert out["next_page_url"] == "http://s.com/news/index_2.html", out["next_page_url"]


class TestRecordDedupAndKnownHit:
    def test_same_url_recorded_once(self, tools):
        captured, store = tools
        url = _seed_candidate(store)
        payload = {"page_url": "", "items_json": json.dumps([{"url": url}]),
                   "next_page_url": ""}
        assert _call(captured["record_news_urls"], payload)["added"] == 1
        assert _call(captured["record_news_urls"], payload)["added"] == 0
        assert len(store.news_items) == 1

    def test_known_url_counts_as_hit(self, tools):
        """命中调用方给的 known_urls 要计数 —— stop_reason 靠它判 hit_known。"""
        captured, store = tools
        url = _seed_candidate(store)
        store.known_norm = normalize_many([url])
        out = _call(captured["record_news_urls"],
                    {"page_url": "", "items_json": json.dumps([{"url": url}]),
                     "next_page_url": ""})
        assert out["known_hit_count"] == 1
        assert store.known_hit_count == 1


class TestFetchListPageBudget:
    def test_rejects_when_page_budget_exhausted(self, tools):
        """超出 max_pages 必须拒绝并给出收尾指令，避免无限翻页烧钱。"""
        captured, store = tools
        store.list_pages = [{"final_url": f"http://s.com/news?p={i}"}
                            for i in range(store.max_pages)]
        out = _call(captured["fetch_list_page"], {"url": "http://s.com/news?p=99"})
        assert out["ok"] is False
        # 必须明确让 Agent 收尾，而不是含糊报错
        assert "save_results" in out["error"]
        assert str(store.max_pages) in out["error"]


# ---------------------------------------------------------------- 硬停

LIST_HTML = """
<html><body>
  <a href="/news/1.html">旧闻一</a>
  <a href="/news/2.html">新闻二</a>
  <a href="/news/?p=2">下一页</a>
</body></html>
"""


def _fake_async_client(html: str = LIST_HTML):
    """把 httpx.AsyncClient 换成假实现，让 fetch_list_page 走完整成功路径。"""

    class _FakeResponse:
        status_code = 200
        text = html
        url = "http://s.com/news"

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        async def get(self, url):
            return _FakeResponse()

    return _FakeClient


class TestFetchStopsOnKnownHit:
    """抓页时命中 known_urls → 命令式硬停（方案 A，不依赖模型自觉）。"""

    def test_known_url_on_page_sets_hard_stop(self, tools, monkeypatch):
        captured, store = tools
        store.known_norm = normalize_many(["http://s.com/news/1.html"])
        monkeypatch.setattr(ct.httpx, "AsyncClient", _fake_async_client())
        result = asyncio.run(captured["fetch_list_page"]({"url": "http://s.com/news"}))
        text = result["content"][0]["text"]
        assert store.pagination_stopped is True
        assert "known_hit_on_page=1" in text
        assert "禁止继续翻页" in text

    def test_hard_stop_rejects_further_fetch(self, tools):
        """置位后任何 fetch_list_page 一律拒绝，并指明 save_results。"""
        captured, store = tools
        store.pagination_stopped = True
        out = _call(captured["fetch_list_page"], {"url": "http://s.com/news/?p=2"})
        assert out["ok"] is False
        assert "禁止继续翻页" in out["error"]
        assert "save_results" in out["error"]

    def test_known_match_after_normalization(self, tools, monkeypatch):
        """known 与页面 href 书写不同、归一后相同 → 仍须命中硬停。"""
        captured, store = tools
        store.known_norm = normalize_many(["https://S.COM/news/1.html#frag"])
        monkeypatch.setattr(ct.httpx, "AsyncClient", _fake_async_client())
        asyncio.run(captured["fetch_list_page"]({"url": "http://s.com/news"}))
        assert store.pagination_stopped is True

    def test_no_known_url_no_stop(self, tools, monkeypatch):
        captured, store = tools
        store.known_norm = normalize_many(["http://s.com/news/999.html"])
        monkeypatch.setattr(ct.httpx, "AsyncClient", _fake_async_client())
        asyncio.run(captured["fetch_list_page"]({"url": "http://s.com/news"}))
        assert store.pagination_stopped is False


class TestHelpers:
    def test_normalize_url_keeps_scheme(self):
        """请求用 URL 必须保留 scheme（与去重键的 normalize 不同）。"""
        assert normalize_url("https://S.com/a/") == "https://s.com/a"

    def test_normalize_url_keeps_slash_with_query(self):
        assert normalize_url("https://s.com/a/?x=1") == "https://s.com/a/?x=1"

    @pytest.mark.parametrize("text,want", [
        ("2026-08-26", "2026-08-26"),
        ("2026/8/6", "2026-08-06"),
        ("2026年8月6日", "2026-08-06"),
        ("发布时间：2026.08.06", "2026-08-06"),
        ("没有日期", None),
        ("", None),
    ])
    def test_normalize_date(self, text, want):
        assert normalize_date(text) == want

    def test_simplify_strips_scripts_and_offsite(self):
        html = """
        <html><body>
          <script>var x = "<a href='/fake'>no</a>";</script>
          <a href="/news/1.html">真实新闻</a>
          <a href="https://other.com/x">外站</a>
          <a href="javascript:void(0)">空</a>
        </body></html>
        """
        out = simplify_list_html(html, "http://s.com/news/")
        assert "/news/1.html" in out
        assert "other.com" not in out      # 外站链接剔除
        assert "fake" not in out           # script 内容不参与
        assert "javascript:" not in out
