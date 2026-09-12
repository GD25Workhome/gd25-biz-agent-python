"""
内容提取器测试（使用 fixture）
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
    
    assert len(summary) <= 110  # 允许一些余量
    assert summary.endswith("...")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
