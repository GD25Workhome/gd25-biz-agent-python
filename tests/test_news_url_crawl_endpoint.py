"""
新端点 /api/v1/huayuan/news-url-crawl 的契约测试。

不真跑 Agent（耗时长且花钱）：把 run_news_crawl_agent 换成 stub，
只验证状态码映射、响应模型、请求校验、并发信号量。

设计文档：华院Agent设计/260914-整体重构/02-gd25侧详细设计.md §3.2 / §3.3
"""
import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.api.schemas.news_url_crawl import (
    MAX_KNOWN_URLS,
    MAX_PAGES_LIMIT,
    NewsUrlCrawlRequest,
    NewsUrlCrawlResponse,
)
import backend.app.api.routes.news_url_crawl as route_mod
from backend.app.config import settings
from backend.domain.news_crawl.exceptions import AgentExecutionError, ListFetchError

SEED = "http://s.com/news"


def _ok_result(**over):
    result = {
        "news_urls": [{"url": "http://s.com/1", "title": "标题", "published_at": "2026-01-01"}],
        "list_pages_fetched": 2,
        "list_page_urls": ["http://s.com/news", "http://s.com/news?p=2"],
        "stop_reason": "hit_known",
        "stats": {
            "candidate_count": 12, "known_hit_count": 3,
            "list_page_urls": ["http://s.com/news"],
            "agent_turns": 9, "agent_cost_usd": 0.31, "duration_ms": 180000,
        },
    }
    result.update(over)
    return result


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_CRAWL_ENABLED", True)
    monkeypatch.setattr(settings, "NEWS_CRAWL_TIMEOUT_SECONDS", 600)


def _call(monkeypatch, impl, **req_kw):
    """把 runner 换成 impl 后调用端点（端点内是 monkeypatch 后的模块全局名）。"""
    monkeypatch.setattr(route_mod, "run_news_crawl_agent", impl)
    req = NewsUrlCrawlRequest(news_list_url=req_kw.pop("news_list_url", SEED), **req_kw)
    return asyncio.run(route_mod.news_url_crawl(req))


class TestRequestValidation:
    def test_rejects_non_url(self):
        with pytest.raises(ValidationError):
            NewsUrlCrawlRequest(news_list_url="not-a-url")

    def test_rejects_max_pages_over_limit(self):
        with pytest.raises(ValidationError):
            NewsUrlCrawlRequest(news_list_url=SEED, max_pages=MAX_PAGES_LIMIT + 1)

    def test_rejects_max_pages_zero(self):
        with pytest.raises(ValidationError):
            NewsUrlCrawlRequest(news_list_url=SEED, max_pages=0)

    def test_rejects_known_urls_over_limit(self):
        with pytest.raises(ValidationError):
            NewsUrlCrawlRequest(
                news_list_url=SEED,
                known_urls=[f"http://s.com/{i}" for i in range(MAX_KNOWN_URLS + 1)],
            )

    def test_defaults(self):
        r = NewsUrlCrawlRequest(news_list_url=SEED)
        assert r.known_urls == []      # 空 = 首次抓取（全量）
        assert r.max_pages == 3        # 默认 3 页，可不传
        assert r.trace_id is None


class TestStatusCodes:
    def test_503_when_disabled(self, monkeypatch):
        monkeypatch.setattr(settings, "NEWS_CRAWL_ENABLED", False)
        with pytest.raises(HTTPException) as ei:
            _call(monkeypatch, lambda **_: None)
        assert ei.value.status_code == 503

    def test_200_happy_path(self, enabled, monkeypatch):
        async def impl(**_):
            return _ok_result()
        resp = _call(monkeypatch, impl, known_urls=["http://s.com/old"])
        assert isinstance(resp, NewsUrlCrawlResponse)
        assert resp.news_urls[0].url == "http://s.com/1"
        assert resp.news_urls[0].published_at == "2026-01-01"
        assert resp.stop_reason == "hit_known"
        assert resp.list_pages_fetched == 2
        assert resp.stats.agent_cost_usd == 0.31
        assert resp.trace_id                     # 未传则自动生成

    def test_trace_id_passthrough(self, enabled, monkeypatch):
        async def impl(**_):
            return _ok_result()
        resp = _call(monkeypatch, impl, trace_id="trace-abc")
        assert resp.trace_id == "trace-abc"

    def test_504_on_timeout(self, enabled, monkeypatch):
        monkeypatch.setattr(settings, "NEWS_CRAWL_TIMEOUT_SECONDS", 0)

        async def slow(**_):
            await asyncio.sleep(5)
        with pytest.raises(HTTPException) as ei:
            _call(monkeypatch, slow)
        assert ei.value.status_code == 504

    def test_502_on_list_fetch_error(self, enabled, monkeypatch):
        async def impl(**_):
            raise ListFetchError("全部列表页抓取失败")
        with pytest.raises(HTTPException) as ei:
            _call(monkeypatch, impl)
        assert ei.value.status_code == 502

    def test_502_on_agent_error(self, enabled, monkeypatch):
        async def impl(**_):
            raise AgentExecutionError("SDK 异常")
        with pytest.raises(HTTPException) as ei:
            _call(monkeypatch, impl)
        assert ei.value.status_code == 502

    def test_502_masks_unexpected_exception(self, enabled, monkeypatch):
        """未预期异常也应转成 502，且详情不外泄内部细节。"""
        async def impl(**_):
            raise RuntimeError("内部炸了")
        with pytest.raises(HTTPException) as ei:
            _call(monkeypatch, impl)
        assert ei.value.status_code == 502


class TestResponseContract:
    def test_empty_result_is_200_not_error(self, enabled, monkeypatch):
        """全量重复 / 末页无新新闻 → 空数组 + 200，调用方据 stop_reason 判断。"""
        async def impl(**_):
            return _ok_result(news_urls=[], stop_reason="no_next")
        resp = _call(monkeypatch, impl)
        assert resp.news_urls == [] and resp.stop_reason == "no_next"

    def test_no_detail_links_is_200(self, enabled, monkeypatch):
        """通道故障返回空列表，但仍是 200 —— 由 stop_reason 表达。"""
        async def impl(**_):
            return _ok_result(news_urls=[], stop_reason="no_detail_links",
                              stats={**_ok_result()["stats"], "candidate_count": 0})
        resp = _call(monkeypatch, impl)
        assert resp.news_urls == [] and resp.stop_reason == "no_detail_links"

    def test_known_urls_and_max_pages_reach_runner(self, enabled, monkeypatch):
        """接口必须把 known_urls / max_pages 原样透传给 Agent。"""
        seen = {}

        async def impl(**kw):
            seen.update(kw)
            return _ok_result()
        _call(monkeypatch, impl, known_urls=["http://s.com/old"],
              max_pages=3, company_name="测试公司", stock_code="600000")
        assert seen["known_urls"] == ["http://s.com/old"]
        assert seen["max_pages"] == 3
        assert seen["company_name"] == "测试公司"
        assert seen["stock_code"] == "600000"
        assert seen["seed_url"] == SEED


class TestConcurrencySemaphore:
    def test_lazy_singleton(self):
        """信号量必须惰性创建（绑定事件循环）且跨调用复用。"""
        s1 = route_mod._get_semaphore()
        s2 = route_mod._get_semaphore()
        assert s1 is s2

    def test_concurrency_actually_capped(self, enabled, monkeypatch):
        """
        上限为 1 时两个并发请求必须串行 —— 否则会同时跑多个付费 Agent。

        ⚠️ 不能断言 Semaphore._value：它语义反常（运行中空信号量读到 1，释放后也读到 1），
        只能靠实测峰值并发数来判断。
        """
        monkeypatch.setattr(settings, "NEWS_CRAWL_MAX_CONCURRENCY", 1)
        monkeypatch.setattr(route_mod, "_AGENT_SEMAPHORE", None)
        monkeypatch.setattr(settings, "NEWS_CRAWL_TIMEOUT_SECONDS", 600)

        peak = 0
        running = 0

        async def impl(**_):
            nonlocal peak, running
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.1)
            running -= 1
            return _ok_result()

        monkeypatch.setattr(route_mod, "run_news_crawl_agent", impl)

        async def two():
            req = NewsUrlCrawlRequest(news_list_url=SEED)
            return await asyncio.gather(
                route_mod.news_url_crawl(req), route_mod.news_url_crawl(req)
            )
        asyncio.run(two())
        assert peak == 1, f"峰值并发 {peak}，上限被突破"

    def test_concurrency_allows_up_to_limit(self, enabled, monkeypatch):
        """上限为 3 时 3 个并发请求应真正并行（信号量别配错成退化成串行）。"""
        monkeypatch.setattr(settings, "NEWS_CRAWL_MAX_CONCURRENCY", 3)
        monkeypatch.setattr(route_mod, "_AGENT_SEMAPHORE", None)
        monkeypatch.setattr(settings, "NEWS_CRAWL_TIMEOUT_SECONDS", 600)

        peak = 0
        running = 0

        async def impl(**_):
            nonlocal peak, running
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.1)
            running -= 1
            return _ok_result()

        monkeypatch.setattr(route_mod, "run_news_crawl_agent", impl)

        async def three():
            req = NewsUrlCrawlRequest(news_list_url=SEED)
            return await asyncio.gather(*[route_mod.news_url_crawl(req) for _ in range(3)])
        asyncio.run(three())
        assert peak == 3, f"峰值并发 {peak}，未达上限"
