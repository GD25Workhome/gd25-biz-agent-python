"""
文章内容提取器
"""
from typing import Optional, Tuple
import trafilatura
from selectolax.parser import HTMLParser
import re


class ContentExtractor:
    """文章内容提取器"""
    
    @staticmethod
    def extract(html: str, url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        提取文章标题、发布时间和正文内容
        
        Args:
            html: HTML 内容
            url: 文章 URL
            
        Returns:
            (title, published_at, content_text)
        """
        title = ContentExtractor._extract_title(html)
        published_at = ContentExtractor._extract_publish_date(html)
        content = ContentExtractor._extract_content(html, url)
        
        return title, published_at, content
    
    @staticmethod
    def _extract_title(html: str) -> Optional[str]:
        """提取标题"""
        parser = HTMLParser(html)
        
        # 优先尝试 <h1>
        h1_nodes = parser.css("h1")
        if h1_nodes:
            title = h1_nodes[0].text(strip=True)
            if title and len(title) > 3:
                return title
        
        # 尝试 class/id 包含 title 的元素
        for selector in [".title", "#title", "[class*='title']", ".article-title"]:
            nodes = parser.css(selector)
            if nodes:
                title = nodes[0].text(strip=True)
                if title and len(title) > 3:
                    return title
        
        # 回退到 <title> 标签
        title_node = parser.css("title")
        if title_node:
            title = title_node[0].text(strip=True)
            # 清理常见的网站后缀
            for suffix in ["-", "|", "_"]:
                if suffix in title:
                    title = title.split(suffix)[0].strip()
            return title
        
        return None
    
    @staticmethod
    def _extract_publish_date(html: str) -> Optional[str]:
        """
        提取发布日期
        
        Returns:
            ISO 格式日期字符串，或 None
        """
        parser = HTMLParser(html)
        
        # 尝试查找日期相关元素
        date_selectors = [
            "time[datetime]",
            ".publish-time", ".pub-time", ".date", ".time",
            "[class*='date']", "[class*='time']",
            "[id*='date']", "[id*='time']"
        ]
        
        for selector in date_selectors:
            nodes = parser.css(selector)
            for node in nodes:
                # 尝试 datetime 属性
                datetime_attr = node.attributes.get("datetime")
                if datetime_attr:
                    return datetime_attr
                
                # 尝试文本内容
                text = node.text(strip=True)
                date_match = re.search(
                    r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日]?",
                    text
                )
                if date_match:
                    year, month, day = date_match.groups()
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        return None
    
    @staticmethod
    def _extract_content(html: str, url: str) -> Optional[str]:
        """
        提取正文内容
        
        优先使用 trafilatura，失败时回退到简单提取
        """
        # 方法 1: trafilatura（高质量提取）
        try:
            content = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
            if content and len(content.strip()) > 50:
                return content.strip()
        except Exception:
            pass
        
        # 方法 2: 简单回退提取
        try:
            parser = HTMLParser(html)
            
            # 尝试常见的正文容器
            content_selectors = [
                ".content", ".article-content", ".article-body",
                "#content", "#article-content",
                "[class*='content']", "article", "main"
            ]
            
            for selector in content_selectors:
                nodes = parser.css(selector)
                if nodes:
                    text = nodes[0].text(strip=True)
                    if len(text) > 50:
                        return text
            
            # 最后尝试 <body>
            body = parser.css("body")
            if body:
                # 移除 script 和 style
                for tag in ["script", "style", "nav", "header", "footer"]:
                    for node in parser.css(tag):
                        node.decompose()
                
                text = body[0].text(strip=True)
                if len(text) > 50:
                    return text
                    
        except Exception:
            pass
        
        return None
    
    @staticmethod
    def generate_summary(content: str, max_length: int = 200) -> str:
        """
        生成内容摘要
        
        简单截取前 N 个字符
        """
        if not content:
            return ""
        
        # 清理多余空白
        summary = " ".join(content.split())
        
        if len(summary) <= max_length:
            return summary
        
        # 截断并添加省略号
        return summary[:max_length].rsplit(" ", 1)[0] + "..."
