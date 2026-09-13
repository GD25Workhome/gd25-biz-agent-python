"""
列表页链接提取器
"""
from typing import List, Set, Tuple, Optional
from urllib.parse import urljoin, urlparse
from selectolax.parser import HTMLParser
import re
from ..models import ListItem


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
    def extract_list_items(html: str, base_url: str, same_domain_only: bool = True) -> List[ListItem]:
        """
        从 HTML 提取新闻列表项，包含 URL、标题、发布日期
        
        Args:
            html: HTML 内容
            base_url: 基础 URL（列表页 URL）
            same_domain_only: 是否仅返回同域名链接
            
        Returns:
            ListItem 对象列表
        """
        parser = HTMLParser(html)
        items: List[ListItem] = []
        seen_urls: Set[str] = set()
        base_domain = urlparse(base_url).netloc.lower()
        
        # 提取所有 <a> 标签
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
            
            # 去重
            if absolute_url in seen_urls:
                continue
            
            # 优先处理包含新闻关键词的链接
            if any(kw in url_lower for kw in ListExtractor.NEWS_KEYWORDS):
                seen_urls.add(absolute_url)
                
                # 尝试从链接或其父容器提取标题和日期
                title, published_at = ListExtractor._extract_metadata_from_link(node)
                
                items.append(ListItem(
                    url=absolute_url,
                    title=title,
                    published_at=published_at
                ))
            # 也保留其他合理的链接（作为候选）
            elif len(urlparse(absolute_url).path) > 1:
                seen_urls.add(absolute_url)
                title, published_at = ListExtractor._extract_metadata_from_link(node)
                items.append(ListItem(
                    url=absolute_url,
                    title=title,
                    published_at=published_at
                ))
        
        # 按新闻关键词优先级排序
        items.sort(key=lambda item: (
            -sum(kw in item.url.lower() for kw in ListExtractor.NEWS_KEYWORDS),
            item.url
        ))
        
        return items
    
    @staticmethod
    def _extract_metadata_from_link(node) -> Tuple[Optional[str], Optional[str]]:
        """
        从链接节点及其父容器提取标题和日期
        
        Returns:
            (title, published_at) 元组
        """
        title = None
        published_at = None
        
        # 获取链接文本作为标题候选
        link_text = node.text(strip=True)
        
        # 尝试从链接文本中分离日期和标题
        # 模式: "2026-08-26 新闻标题" 或 "2026年8月26日 新闻标题"
        date_title_match = re.match(
            r'^(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)\s+(.+)$',
            link_text
        )
        if date_title_match:
            date_str, title_str = date_title_match.groups()
            published_at = ListExtractor._normalize_date(date_str)
            title = title_str.strip()
        else:
            # 如果没有日期前缀，整个文本作为标题
            if link_text and len(link_text) > 3:
                title = link_text
        
        # 尝试从父容器或兄弟元素中查找日期
        if not published_at:
            parent = node.parent
            if parent:
                # 查找父容器中的日期元素
                parent_text = parent.text(strip=True)
                date_match = re.search(
                    r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日]?',
                    parent_text
                )
                if date_match:
                    year, month, day = date_match.groups()
                    published_at = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        return title, published_at
    
    @staticmethod
    def _normalize_date(date_str: str) -> Optional[str]:
        """
        规范化日期字符串为 YYYY-MM-DD 格式
        
        支持格式:
        - 2026-08-26
        - 2026/08/26
        - 2026年8月26日
        """
        match = re.search(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日]?', date_str)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return None
    
    @staticmethod
    def extract_pagination_links(html: str, base_url: str) -> List[str]:
        """
        提取分页链接
        
        Args:
            html: HTML 内容
            base_url: 当前页 URL
            
        Returns:
            下一页或分页索引 URL 列表
        """
        parser = HTMLParser(html)
        pagination_urls: Set[str] = set()
        base_domain = urlparse(base_url).netloc.lower()
        
        # 常见分页模式
        pagination_selectors = [
            "a.next", "a.page-next", "a[rel='next']",
            ".pagination a", ".pager a", ".page-nav a",
            "[class*='pagination'] a", "[class*='pager'] a"
        ]
        
        # 分页链接关键词
        pagination_keywords = ["next", "下一页", "page=", "index_", "/p/", "/page/"]
        
        for selector in pagination_selectors:
            nodes = parser.css(selector)
            for node in nodes:
                href = node.attributes.get("href", "").strip()
                if not href or href.startswith("#"):
                    continue
                
                absolute_url = urljoin(base_url, href)
                
                # 同域名检查
                link_domain = urlparse(absolute_url).netloc.lower()
                if link_domain != base_domain:
                    continue
                
                # 检查是否包含分页特征
                url_lower = absolute_url.lower()
                node_text = node.text(strip=True).lower()
                
                if (any(kw in url_lower for kw in pagination_keywords) or
                    any(kw in node_text for kw in pagination_keywords) or
                    re.search(r'(page|p|index)[\-_=]\d+', url_lower)):
                    pagination_urls.add(absolute_url)
        
        return sorted(list(pagination_urls))
    
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
