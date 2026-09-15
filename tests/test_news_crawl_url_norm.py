"""
URL 归一化单测。

⚠️ 本文件是跨语言契约测试：Python 的 normalize() 必须与
exhibition 侧 Java 的 RadarUrlNormUtil.normalize() 结果逐字符一致，
否则 L1 提示词命中与 L2 过滤会失效（同一 URL 被当成两条）。

设计文档：华院Agent设计/260914-整体重构/02-gd25侧详细设计.md §4.3
"""
from backend.domain.news_crawl.url_norm import normalize, normalize_many


class TestNormalizeHost:
    def test_host_lowercased(self):
        assert normalize("https://WWW.Example.COM/A") == "www.example.com/A"

    def test_scheme_dropped(self):
        """http/https 归一（同站同页不因协议不同算两条）。"""
        assert normalize("http://s.com/a") == normalize("https://s.com/a")

    def test_www_not_stripped(self):
        """⚠️ 刻意不剥 www. —— 与 Java 侧保持一致，两边都别自作聪明。"""
        assert normalize("https://www.s.com/a") == "www.s.com/a"
        assert normalize("https://www.s.com/a") != normalize("https://s.com/a")


class TestNormalizePath:
    def test_trailing_slash_stripped_without_query(self):
        assert normalize("http://s.com/news/") == "s.com/news"

    def test_trailing_slash_kept_with_query(self):
        """⚠️ 有 query 时保留尾斜杠，否则会与真实路由不符。"""
        assert normalize("http://s.com/news/?id=1") == "s.com/news/?id=1"

    def test_bare_host_and_slash_root_are_same(self):
        """
        `http://s.com` 与 `http://s.com/` 归一到同一个键 `s.com/`。

        ⚠️ 根路径的 `/` 不会被规则 3 去掉（`len(path) > 1` 保护），
        无 path 的裸 host 也会补成 `/`，因此两者一致 —— 这是刻意的：
        新闻站点入口页常以裸域名给出，若与带斜杠版本算两条，去重会漏。

        Java 侧 RadarUrlNormUtil 必须产出同样结果，否则跨语言去重失效。
        """
        assert normalize("http://s.com") == "s.com/"
        assert normalize("http://s.com/") == "s.com/"
        assert normalize("http://s.com") == normalize("http://s.com/")

    def test_path_case_preserved(self):
        assert normalize("http://s.com/News/Index") == "s.com/News/Index"


class TestNormalizeQuery:
    def test_query_order_normalized(self):
        """参数顺序不同 → 同一条。"""
        a = normalize("http://s.com/a?b=1&a=2")
        b = normalize("http://s.com/a?a=2&b=1")
        assert a == b == "s.com/a?a=2&b=1"

    def test_bare_query_kept_verbatim(self):
        """
        ⚠️ 华岭特例：/news/html/?109.html 的 query 是 `109.html`（无 `=`）。

        不能用 parse_qsl + urlencode —— 那会把 `109.html` 补成 `109.html=`，
        导致该站全部详情页归一化后变成同一个 key，去重直接失效。
        """
        assert normalize("https://s.com/news/html/?109.html") == "s.com/news/html/?109.html"

    def test_trailing_ampersand_dropped(self):
        assert normalize("http://s.com/a?b=1&") == "s.com/a?b=1"

    def test_duplicate_params_kept(self):
        """重复参数不去重（顺序即语义，如 ?tag=a&tag=b 与 ?tag=b&tag=a 不同页）。"""
        assert normalize("http://s.com/a?tag=b&tag=a") == "s.com/a?tag=a&tag=b"

    def test_empty_query_no_question_mark(self):
        assert "?" not in normalize("http://s.com/a?")


class TestNormalizeRobustness:
    def test_empty_and_blank(self):
        assert normalize("") == ""
        assert normalize("   ") == ""
        assert normalize(None) == ""

    def test_fragment_dropped(self):
        assert normalize("http://s.com/a#section") == "s.com/a"

    def test_relative_url_returned_asis(self):
        """无 netloc 的相对路径原样返回（不构造假的 host）。"""
        assert normalize("/news/1.html") == "/news/1.html"

    def test_never_raises(self):
        for weird in ["http://", "://", "ht tp://a b/c", "\x00", "https://s.com:99999/a"]:
            normalize(weird)  # 不抛异常即可

    def test_idempotent(self):
        """归一化必须是幂等的 —— 后端会反复归一同一批 URL。"""
        for url in ["https://WWW.S.com/news/?b=1&a=2", "http://s.com/news/html/?109.html",
                    "http://s.com/a", "/rel/path"]:
            once = normalize(url)
            assert normalize(once) == once, url


class TestNormalizeMany:
    def test_returns_set_and_dedups(self):
        got = normalize_many([
            "http://s.com/a",
            "https://s.com/a/",       # 同一条
            "http://S.COM/a#x",       # 同一条
            "http://s.com/b",
        ])
        assert got == {"s.com/a", "s.com/b"}

    def test_empty_input(self):
        assert normalize_many([]) == set()

    def test_mixed_garbage_ignored(self):
        """空串不入集合。"""
        assert normalize_many(["", "  ", "http://s.com/a"]) == {"s.com/a"}
