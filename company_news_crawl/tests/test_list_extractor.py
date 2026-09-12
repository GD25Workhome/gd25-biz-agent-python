"""
列表提取器单元测试
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
