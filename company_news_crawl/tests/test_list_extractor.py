"""
列表提取器单元测试 - 增强版
支持 list-with-date 场景（Ping An 等站点）
"""
import pytest
from company_news_crawl.adapters.list_extractor import ListExtractor


def test_extract_links_basic():
    """测试基本链接提取"""
    html = """
    <html>
    <body>
        <a href="/news/detail/123">新闻标题1</a>
        <a href="/news/detail/456">新闻标题2</a>
        <a href="/about">关于我们</a>
        <a href="javascript:void(0)">无效链接</a>
    </body>
    </html>
    """
    base_url = "https://example.com/news"
    
    links = ListExtractor.extract_links(html, base_url, same_domain_only=True)
    
    assert len(links) >= 2
    assert any("detail/123" in link for link in links)
    assert any("detail/456" in link for link in links)
    assert not any("javascript:" in link for link in links)


def test_normalize_url():
    """测试 URL 规范化"""
    url1 = "HTTP://Example.COM/News/Detail/123#comment"
    normalized1 = ListExtractor.normalize_url(url1)
    assert normalized1 == "http://example.com/News/Detail/123"
    
    url2 = "https://example.com/news/"
    normalized2 = ListExtractor.normalize_url(url2)
    assert normalized2 == "https://example.com/news"
    
    url3 = "https://example.com/"
    normalized3 = ListExtractor.normalize_url(url3)
    assert normalized3 == "https://example.com/"


def test_extract_links_same_domain_filter():
    """测试同域名过滤"""
    html = """
    <html>
    <body>
        <a href="/news/1">本站新闻</a>
        <a href="https://other.com/news/2">外站新闻</a>
    </body>
    </html>
    """
    base_url = "https://example.com/list"
    
    links = ListExtractor.extract_links(html, base_url, same_domain_only=True)
    
    assert all("example.com" in link for link in links)
    assert not any("other.com" in link for link in links)


def test_extract_links_keywords_priority():
    """测试关键词优先级"""
    html = """
    <html>
    <body>
        <a href="/about">关于我们</a>
        <a href="/news/detail/123">新闻详情</a>
        <a href="/xinwen/456">公司动态</a>
    </body>
    </html>
    """
    base_url = "https://example.com/"
    
    links = ListExtractor.extract_links(html, base_url)
    
    # 包含新闻关键词的链接应该排在前面
    assert "news" in links[0].lower() or "xinwen" in links[0].lower()


def test_extract_list_items_with_date_in_anchor():
    """测试从锚点文本提取日期和标题（Ping An 模式）"""
    html = """
    <html>
    <body>
        <div class="news-list">
            <a href="/news/001">2026-08-26 平安银行发布中报</a>
            <a href="/news/002">2026年8月15日 推出新产品</a>
            <a href="/news/003">2026/08/01 金融科技峰会</a>
        </div>
    </body>
    </html>
    """
    base_url = "https://bank.example.com/news"
    
    items = ListExtractor.extract_list_items(html, base_url)
    
    assert len(items) >= 3
    
    # 检查第一项
    item1 = next((item for item in items if "001" in item.url), None)
    assert item1 is not None
    assert item1.title == "平安银行发布中报"
    assert item1.published_at == "2026-08-26"
    
    # 检查第二项（中文日期格式）
    item2 = next((item for item in items if "002" in item.url), None)
    assert item2 is not None
    assert item2.title == "推出新产品"
    assert item2.published_at == "2026-08-15"
    
    # 检查第三项（斜杠分隔）
    item3 = next((item for item in items if "003" in item.url), None)
    assert item3 is not None
    assert item3.published_at == "2026-08-01"


def test_extract_list_items_from_pingan_fixture():
    """测试从 Ping An 风格的 fixture 提取列表项"""
    with open("company_news_crawl/tests/fixtures/pingan_list_page.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    base_url = "http://bank.pingan.com/about/news"
    items = ListExtractor.extract_list_items(html, base_url)
    
    # 应该提取到 3 条新闻（排除组织架构、联系方式等导航链接）
    news_items = [item for item in items if "news" in item.url or "gsxw" in item.url]
    assert len(news_items) >= 3
    
    # 检查日期提取
    dated_items = [item for item in news_items if item.published_at]
    assert len(dated_items) >= 3
    
    # 检查标题提取
    titled_items = [item for item in news_items if item.title]
    assert len(titled_items) >= 3


def test_extract_pagination_links():
    """测试分页链接提取"""
    html = """
    <html>
    <body>
        <div class="pagination">
            <a href="/news/page/1" class="current">1</a>
            <a href="/news/page/2">2</a>
            <a href="/news/page/3">3</a>
            <a href="/news/page/2" class="next">下一页</a>
        </div>
    </body>
    </html>
    """
    base_url = "http://example.com/news/page/1"
    
    pagination_links = ListExtractor.extract_pagination_links(html, base_url)
    
    assert len(pagination_links) >= 2
    assert any("page/2" in link for link in pagination_links)
    assert any("page/3" in link for link in pagination_links)


def test_extract_pagination_from_pingan_fixture():
    """测试从 Ping An fixture 提取分页链接"""
    with open("company_news_crawl/tests/fixtures/pingan_list_page.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    base_url = "http://bank.pingan.com/about/news"
    pagination_links = ListExtractor.extract_pagination_links(html, base_url)
    
    # 应该提取到至少 2 个分页链接
    assert len(pagination_links) >= 2
    assert any("page/2" in link for link in pagination_links)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
