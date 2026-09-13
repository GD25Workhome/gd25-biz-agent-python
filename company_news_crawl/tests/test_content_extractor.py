"""
内容提取器测试 - 增强版
支持 h5 日期、h3 标题、导航标题过滤、列表元数据回退
"""
import pytest
from company_news_crawl.adapters.content_extractor import ContentExtractor


def test_extract_title_from_fixture():
    """测试从 fixture 提取标题"""
    with open("company_news_crawl/tests/fixtures/article_page.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    title, _, _ = ContentExtractor.extract(html, "https://example.com/news/001")
    
    assert title is not None
    assert "年度报告" in title


def test_extract_content_from_fixture():
    """测试从 fixture 提取正文"""
    with open("company_news_crawl/tests/fixtures/article_page.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    _, _, content = ContentExtractor.extract(html, "https://example.com/news/001")
    
    assert content is not None
    assert len(content) > 50
    assert "营业收入" in content or "创新" in content


def test_generate_summary():
    """测试摘要生成"""
    long_text = "这是一个很长的文本内容。" * 50
    
    summary = ContentExtractor.generate_summary(long_text, max_length=100)
    
    assert len(summary) <= 110
    assert summary.endswith("...")


def test_extract_h3_title_and_h5_date():
    """测试从 h3 提取标题、从 h5 提取日期（Ping An 模式）"""
    with open("company_news_crawl/tests/fixtures/pingan_article_with_h5_date.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    title, published_at, content = ContentExtractor.extract(html, "http://bank.pingan.com/news/001")
    
    # 标题应该从 h3 提取
    assert title is not None
    assert "平安银行发布2026年中报" in title
    
    # 日期应该从 h5 提取
    assert published_at is not None
    assert published_at == "2026-08-26"
    
    # 内容应该正常提取
    assert content is not None
    assert "营业收入" in content or "零售客户" in content


def test_avoid_nav_titles():
    """测试避免提取导航标题"""
    with open("company_news_crawl/tests/fixtures/pingan_nav_page.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    # 不提供列表页标题，应该识别「组织架构」为导航标题
    title, _, _ = ContentExtractor.extract(html, "http://bank.pingan.com/about/architecture")
    
    # 「组织架构」应该被识别为导航标题，返回 None 或页面 title
    # 如果是页面 title，应该被清理过
    if title:
        assert title != "组织架构"


def test_list_metadata_fallback():
    """测试列表页元数据作为回退"""
    html = """
    <html>
    <head><title>新闻详情</title></head>
    <body>
        <article>
            <div class="content">
                <p>这是一篇没有明确标题和日期标记的文章内容。</p>
                <p>但我们从列表页已经获取了这些信息。文章正文需要足够长才能被提取器识别为有效内容。</p>
                <p>这里添加更多内容使其超过最小长度要求。我们测试的是列表页元数据回退机制。</p>
            </div>
        </article>
    </body>
    </html>
    """
    
    list_title = "从列表页提取的标题"
    list_date = "2026-08-26"
    
    title, published_at, content = ContentExtractor.extract(
        html, 
        "http://example.com/news/001",
        list_title=list_title,
        list_date=list_date
    )
    
    # 应该使用列表页提供的元数据
    assert title == list_title
    assert published_at == list_date
    # 内容应该被提取（虽然没有明确标记）
    assert content is not None
    assert len(content) > 20


def test_list_metadata_override_nav_title():
    """测试列表页标题覆盖导航标题"""
    with open("company_news_crawl/tests/fixtures/pingan_nav_page.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    list_title = "这是真实的新闻标题"
    list_date = "2026-08-26"
    
    title, published_at, _ = ContentExtractor.extract(
        html,
        "http://bank.pingan.com/about/architecture",
        list_title=list_title,
        list_date=list_date
    )
    
    # 应该使用列表页标题而不是页面中的「组织架构」
    assert title == list_title
    assert published_at == list_date


def test_extract_date_chinese_format():
    """测试提取中文日期格式"""
    html = """
    <html>
    <body>
        <div class="article">
            <h3>测试文章</h3>
            <span class="date">发布时间：2026年8月26日</span>
            <div class="content">文章内容</div>
        </div>
    </body>
    </html>
    """
    
    _, published_at, _ = ContentExtractor.extract(html, "http://example.com/news/001")
    
    assert published_at == "2026-08-26"


def test_extract_date_multiple_formats():
    """测试多种日期格式"""
    test_cases = [
        ("2026-08-26", "2026-08-26"),
        ("2026/08/26", "2026-08-26"),
        ("2026年8月26日", "2026-08-26"),
        ("2026-8-6", "2026-08-06"),
    ]
    
    for date_text, expected in test_cases:
        html = f"""
        <html>
        <body>
            <h5>{date_text}</h5>
            <div class="content">内容</div>
        </body>
        </html>
        """
        
        _, published_at, _ = ContentExtractor.extract(html, "http://example.com/test")
        assert published_at == expected, f"Failed for {date_text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
