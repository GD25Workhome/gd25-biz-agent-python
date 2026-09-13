#!/usr/bin/env python3
"""
验证 list-with-date 功能的集成测试脚本
"""
from company_news_crawl.adapters.list_extractor import ListExtractor
from company_news_crawl.adapters.content_extractor import ContentExtractor

def test_list_extraction():
    """测试列表提取功能"""
    print("=== 测试 1: 列表项结构化提取 ===")
    
    with open("company_news_crawl/tests/fixtures/pingan_list_page.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    base_url = "http://bank.pingan.com/news"
    items = ListExtractor.extract_list_items(html, base_url)
    
    print(f"提取到 {len(items)} 个列表项")
    
    news_items = [item for item in items if "news" in item.url or "gsxw" in item.url]
    print(f"其中新闻项 {len(news_items)} 个")
    
    for i, item in enumerate(news_items[:3], 1):
        print(f"\n项目 {i}:")
        print(f"  URL: {item.url}")
        print(f"  标题: {item.title}")
        print(f"  日期: {item.published_at}")
    
    assert len(news_items) >= 3, "应该提取到至少 3 个新闻项"
    dated_items = [item for item in news_items if item.published_at]
    assert len(dated_items) >= 3, "应该提取到至少 3 个带日期的项"
    print("\n✅ 列表提取测试通过")


def test_pagination():
    """测试分页提取功能"""
    print("\n=== 测试 2: 分页链接提取 ===")
    
    with open("company_news_crawl/tests/fixtures/pingan_list_page.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    base_url = "http://bank.pingan.com/news"
    pagination_links = ListExtractor.extract_pagination_links(html, base_url)
    
    print(f"提取到 {len(pagination_links)} 个分页链接:")
    for link in pagination_links[:5]:
        print(f"  - {link}")
    
    assert len(pagination_links) >= 2, "应该提取到至少 2 个分页链接"
    print("\n✅ 分页提取测试通过")


def test_content_extraction_with_fallback():
    """测试内容提取与元数据回退"""
    print("\n=== 测试 3: 内容提取 + 元数据回退 ===")
    
    # 测试 3.1: h3 标题 + h5 日期
    with open("company_news_crawl/tests/fixtures/pingan_article_with_h5_date.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    title, date, content = ContentExtractor.extract(html, "http://bank.pingan.com/news/001")
    
    print(f"\n详情页提取:")
    print(f"  标题: {title}")
    print(f"  日期: {date}")
    print(f"  正文长度: {len(content) if content else 0}")
    
    assert "平安银行发布2026年中报" in title, "应该提取到 h3 标题"
    assert date == "2026-08-26", "应该提取到 h5 日期"
    assert content and len(content) > 50, "应该提取到正文"
    
    # 测试 3.2: 导航标题过滤
    with open("company_news_crawl/tests/fixtures/pingan_nav_page.html", "r", encoding="utf-8") as f:
        nav_html = f.read()
    
    list_title = "这是真实的新闻标题"
    list_date = "2026-08-26"
    
    title2, date2, _ = ContentExtractor.extract(
        nav_html,
        "http://bank.pingan.com/about/architecture",
        list_title=list_title,
        list_date=list_date
    )
    
    print(f"\n导航页面 + 列表元数据:")
    print(f"  标题: {title2}")
    print(f"  日期: {date2}")
    
    assert title2 == list_title, "应该使用列表页标题而非「组织架构」"
    assert date2 == list_date, "应该使用列表页日期"
    
    print("\n✅ 内容提取测试通过")


def test_date_formats():
    """测试多种日期格式"""
    print("\n=== 测试 4: 日期格式支持 ===")
    
    test_cases = [
        ("2026-08-26", "2026-08-26"),
        ("2026/08/26", "2026-08-26"),
        ("2026年8月26日", "2026-08-26"),
        ("2026-8-6", "2026-08-06"),
    ]
    
    for input_date, expected in test_cases:
        html = f"""
        <html>
        <body>
            <h5>{input_date}</h5>
            <article><p>这是测试文章内容，需要足够长才能被提取器识别为有效正文。我们正在测试日期格式的规范化功能。</p></article>
        </body>
        </html>
        """
        
        _, date, _ = ContentExtractor.extract(html, "http://example.com/test")
        print(f"  {input_date:20s} -> {date}")
        assert date == expected, f"日期格式转换失败: {input_date}"
    
    print("\n✅ 日期格式测试通过")


if __name__ == "__main__":
    print("=" * 60)
    print("company_news_crawl list-with-date 功能验证")
    print("=" * 60)
    
    test_list_extraction()
    test_pagination()
    test_content_extraction_with_fallback()
    test_date_formats()
    
    print("\n" + "=" * 60)
    print("✅ 所有集成测试通过！")
    print("=" * 60)
