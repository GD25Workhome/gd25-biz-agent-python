"""
列表页链接提取器
"""
from typing import List, Set
from urllib.parse import urljoin, urlparse
from selectolax.parser import HTMLParser


class ListExtractor:
    """新闻列表链接提取器"""
    
    # 新闻链接特征关键词
    NEWS_KEYWORDS = [
        "news", "xinwen", "gsxw", "detail", "article", "content",
        "info", "notice", "announcement", "view", "show", "read",
        "dongtai", "zixun"
    ]
    
    # 排除的路径关键词
    EXCLUDE_KEYWORDS = [
        "login", "register", "search", "download", "pdf", "doc",
        "jpg", "jpeg", "png", "gif", "css", "js", "javascript:"
    ]
    
    @staticmethod
    def extract_links(html: str, base_url: str, same_domain_only: bool = True) -> List[str]:
        """
        从 HTML 提取新闻文章候选链接
        
        Args:
            html: HTML 内容
            base_url: 基础 URL（列表页 URL）
            same_domain_only: 是否仅返回同域名链接
            
        Returns:
            去重后的链接列表
        """
        parser = HTMLParser(html)
        links: Set[str] = set()
        base_domain = urlparse(base_url).netloc.lower()
        
        # 提取所有 <a> 标签的 href
        for node in parser.css("a[href]"):
            href = node.attributes.get("href", "").strip()
            if not href or href.startswith("#"):
                continue
            
            # 解析为绝对 URL
            absolute_url = urljoin(base_url, href)
            
            # 检查域名
            if same_domain_only:
                link_domain = urlparse(absolute_url).netloc.lower()
                if link_domain != base_domain:
                    continue
            
            # 检查协议
            if not absolute_url.startswith(("http://", "https://")):
                continue
            
            # 排除明显的非文章链接
            url_lower = absolute_url.lower()
            if any(kw in url_lower for kw in ListExtractor.EXCLUDE_KEYWORDS):
                continue
            
            # 优先保留包含新闻关键词的链接
            if any(kw in url_lower for kw in ListExtractor.NEWS_KEYWORDS):
                links.add(absolute_url)
            # 也保留其他合理的链接（作为候选）
            elif len(urlparse(absolute_url).path) > 1:
                links.add(absolute_url)
        
        # 返回排序后的列表（优先新闻关键词）
        sorted_links = sorted(
            links,
            key=lambda u: (
                -sum(kw in u.lower() for kw in ListExtractor.NEWS_KEYWORDS),
                u
            )
        )
        
        return sorted_links
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """
        规范化 URL
        
        - 转小写域名
        - 去除 fragment (#)
        - 去除尾部斜杠
        """
        parsed = urlparse(url)
        
        # 重构 URL
        normalized = f"{parsed.scheme}://{parsed.netloc.lower()}{parsed.path}"
        
        # 保留 query string（如果有）
        if parsed.query:
            normalized += f"?{parsed.query}"
        
        # 去除尾部斜杠（除非是根路径）
        if normalized.endswith("/") and len(parsed.path) > 1:
            normalized = normalized[:-1]
        
        return normalized
    
    @staticmethod
    def filter_by_distance(links: List[str], base_url: str, max_distance: int = 3) -> List[str]:
        """
        根据 URL 路径层级距离过滤链接
        
        Args:
            links: 链接列表
            base_url: 基础 URL
            max_distance: 最大允许的路径层级差异
            
        Returns:
            过滤后的链接列表
        """
        base_depth = len(urlparse(base_url).path.strip("/").split("/"))
        
        filtered = []
        for link in links:
            link_depth = len(urlparse(link).path.strip("/").split("/"))
            if abs(link_depth - base_depth) <= max_distance:
                filtered.append(link)
        
        return filtered
