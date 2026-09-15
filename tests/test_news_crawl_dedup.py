"""
三层去重与停止原因判定单测。

L1 提示词短路：known_urls 塞进 user prompt，让 Agent 看到熟人就不再翻页
L2 返回前过滤：new_items() 只吐 known 之外的
L3 由 exhibition 落库唯一索引兜底（不在本服务范围）

设计文档：华院Agent设计/260914-整体重构/02-gd25侧详细设计.md §4.3 / §4.8
"""
from backend.domain.news_crawl.agent_runner import decide_stop_reason
from backend.domain.news_crawl.crawl_tools import CrawlStore, NewsItem
from backend.domain.news_crawl.prompts import (
    KNOWN_URLS_EMPTY,
    KNOWN_URLS_PROMPT_LIMIT,
    build_known_urls_block,
    build_user_prompt,
)
from backend.domain.news_crawl.url_norm import normalize_many


def _item(url: str, title: str = "", date: str | None = None) -> NewsItem:
    return NewsItem(url=url, title=title, published_at=date, list_page_url="http://s.com/news")


def _store(**kw) -> CrawlStore:
    return CrawlStore(seed_url="http://s.com/news", max_pages=8, **kw)


class TestL1PromptShortCircuit:
    def test_empty_known_uses_first_run_wording(self):
        """首次抓取必须明确告诉 Agent "无已知，尽量抓满"，否则它会早早收工。"""
        assert KNOWN_URLS_EMPTY in build_known_urls_block([])

    def test_known_urls_are_inlined(self):
        block = build_known_urls_block(["http://s.com/old1", "http://s.com/old2"])
        assert "http://s.com/old1" in block and "http://s.com/old2" in block

    def test_prompt_block_is_capped(self):
        """known_urls 全部塞进去会把提示词撑爆，超出部分截断（L2 仍会兜住）。"""
        urls = [f"http://s.com/{i}" for i in range(KNOWN_URLS_PROMPT_LIMIT + 50)]
        block = build_known_urls_block(urls)
        assert f"http://s.com/{KNOWN_URLS_PROMPT_LIMIT - 1}" in block
        assert f"http://s.com/{KNOWN_URLS_PROMPT_LIMIT}" not in block

    def test_user_prompt_carries_seed_and_known(self):
        p = build_user_prompt(
            seed_url="http://s.com/news", known_urls=["http://s.com/old"],
            company_name="测试公司", stock_code="600000", max_pages=8,
        )
        assert "http://s.com/news" in p
        assert "http://s.com/old" in p
        assert "测试公司" in p and "600000" in p

    def test_user_prompt_without_company(self):
        """公司名为空时不能渲染出 "None" 之类的字面量。"""
        p = build_user_prompt(seed_url="http://s.com/news", known_urls=[],
                              company_name="", stock_code="", max_pages=5)
        assert "None" not in p


class TestL2ReturnFilter:
    def test_new_items_excludes_known(self):
        s = _store(known_norm=normalize_many(["http://s.com/old"]))
        s.news_items = [_item("http://s.com/old", "旧"), _item("http://s.com/new", "新")]
        assert [i.url for i in s.new_items()] == ["http://s.com/new"]

    def test_new_items_matches_after_normalization(self):
        """known 与抓到的 URL 书写不同、归一后相同 → 仍须判为重复。"""
        s = _store(known_norm=normalize_many(["https://S.COM/a/"]))
        s.news_items = [_item("http://s.com/a")]
        assert s.new_items() == []

    def test_news_urls_respects_exclude_known_flag(self):
        s = _store(known_norm=normalize_many(["http://s.com/old"]))
        s.news_items = [_item("http://s.com/old"), _item("http://s.com/new")]
        assert s.news_urls() == ["http://s.com/new"]
        assert len(s.news_urls(exclude_known=False)) == 2

    def test_all_known_yields_empty(self):
        """全量重复（本轮无新新闻）是正常结果，不是错误。"""
        s = _store(known_norm=normalize_many(["http://s.com/1", "http://s.com/2"]))
        s.news_items = [_item("http://s.com/1"), _item("http://s.com/2")]
        assert s.new_items() == []

    def test_first_run_returns_everything(self):
        s = _store()
        s.news_items = [_item("http://s.com/1"), _item("http://s.com/2")]
        assert len(s.new_items()) == 2


class TestStopReason:
    """⚠️ 判断顺序是关键：no_detail_links 必须先判。"""

    def test_channel_failure_reported_as_no_detail_links(self):
        """抓到页面却零链接 = 通道故障（可能需 JS 渲染），不能报成 normal 末页。"""
        s = _store(list_pages=[{"final_url": "http://s.com/news"}])
        assert decide_stop_reason(s, 8) == "no_detail_links"

    def test_no_detail_links_precedes_hit_known(self):
        """零链接且同时命中 known 时，通道故障优先暴露。"""
        s = _store(list_pages=[{"final_url": "http://s.com/news"}], known_hit_count=5)
        assert decide_stop_reason(s, 8) == "no_detail_links"

    def test_hit_known(self):
        s = _store(list_pages=[{"final_url": "http://s.com/news"}], known_hit_count=1,
                   news_items=[_item("http://s.com/new")])
        assert decide_stop_reason(s, 8) == "hit_known"

    def test_hit_known_by_fetch_detection_alone(self):
        """
        抓页时检测到已知 URL 即置位硬停。Agent 可能只把新 URL 记进
        record_news_urls（不记录已知 URL），此时 known_hit_count=0，
        必须靠 pagination_stopped 判成 hit_known。
        """
        s = _store(list_pages=[{"final_url": "http://s.com/news"}],
                   pagination_stopped=True,
                   news_items=[_item("http://s.com/new")])
        assert decide_stop_reason(s, 8) == "hit_known"

    def test_hit_known_when_only_deduped_items_remain(self):
        """命中的都是旧新闻、new_items 为空 —— 仍应是 hit_known 而非 no_next。"""
        s = _store(known_norm=normalize_many(["http://s.com/old"]),
                   list_pages=[{"final_url": "http://s.com/news"}], known_hit_count=1)
        s.news_items = [_item("http://s.com/old")]
        assert decide_stop_reason(s, 8) == "hit_known"

    def test_max_pages(self):
        s = _store(list_pages=[{"final_url": f"http://s.com/n{i}"} for i in range(8)],
                   news_items=[_item("http://s.com/1")])
        assert decide_stop_reason(s, 8) == "max_pages"

    def test_no_next_when_reached_last_page(self):
        s = _store(list_pages=[{"final_url": "http://s.com/n1"},
                               {"final_url": "http://s.com/n2"}],
                   news_items=[_item("http://s.com/1")])
        assert decide_stop_reason(s, 8) == "no_next"

    def test_max_pages_boundary(self):
        """页数 == 上限即算触顶，不能等超过。"""
        s = _store(list_pages=[{"final_url": "http://s.com/n"}],
                   news_items=[_item("http://s.com/1")])
        assert decide_stop_reason(s, 1) == "max_pages"
