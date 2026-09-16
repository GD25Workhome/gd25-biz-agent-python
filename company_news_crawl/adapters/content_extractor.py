"""
文章内容提取器
"""
from dataclasses import dataclass
from typing import Optional, Tuple
import hashlib
import trafilatura
from selectolax.parser import HTMLParser
import re


@dataclass(frozen=True)
class ExtractedArticle:
    """
    服务化输出：一篇详情页文章的抽取结果（雷达新闻知识库写链路用）。

    ⚠️ 与 `ContentExtractor.extract()` 的三元组返回值并存，不改原签名 ——
    原三元组是 news 抓取链路（`pipeline/crawl_one.py`）在用的，动了会破坏调用方。

    字段与 exhibition `radar_company_news_document` 表对齐（§4.2）：
        title / published_at / content_text / content_summary / content_hash
    """

    url: str
    title: Optional[str]
    published_at: Optional[str]
    content_text: Optional[str]
    content_summary: str
    content_hash: Optional[str]

    @property
    def ok(self) -> bool:
        """是否具备入库条件（至少要有正文）。"""
        return bool(self.content_text and self.content_text.strip())

    def satisfies(self, min_chars: int) -> bool:
        """
        是否满足最小正文长度要求。

        Args:
            min_chars: 正文最少字符数（低于此值判定为规则抓取失败，交给 Agent 兜底）
        """
        return bool(self.content_text) and len(self.content_text.strip()) >= int(min_chars)


class ContentExtractor:
    """文章内容提取器"""

    @staticmethod
    def extract(html: str, url: str, list_title: Optional[str] = None, 
                list_date: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        提取文章标题、发布时间和正文内容
        
        Args:
            html: HTML 内容
            url: 文章 URL
            list_title: 从列表页提取的标题（作为回退）
            list_date: 从列表页提取的日期（作为回退）
            
        Returns:
            (title, published_at, content_text)
        """
        title = ContentExtractor._extract_title(html, list_title)
        published_at = ContentExtractor._extract_publish_date(html, list_date)
        content = ContentExtractor._extract_content(html, url)
        
        return title, published_at, content
    
    @staticmethod
    def _extract_title(html: str, fallback_title: Optional[str] = None) -> Optional[str]:
        """
        提取标题
        
        Args:
            html: HTML 内容
            fallback_title: 回退标题（来自列表页）
        """
        parser = HTMLParser(html)
        
        # 优先尝试 <h3>（Ping An 等站点常用）
        h3_nodes = parser.css("h3")
        if h3_nodes:
            title = h3_nodes[0].text(strip=True)
            if title and len(title) > 3 and not ContentExtractor._is_nav_title(title):
                return title
        
        # 尝试 <h1>
        h1_nodes = parser.css("h1")
        if h1_nodes:
            title = h1_nodes[0].text(strip=True)
            if title and len(title) > 3 and not ContentExtractor._is_nav_title(title):
                return title
        
        # 尝试 class/id 包含 title 的元素
        for selector in [".title", "#title", "[class*='title']", ".article-title"]:
            nodes = parser.css(selector)
            if nodes:
                title = nodes[0].text(strip=True)
                if title and len(title) > 3 and not ContentExtractor._is_nav_title(title):
                    return title
        
        # 如果有列表页提供的标题，作为回退
        if fallback_title and len(fallback_title) > 3:
            return fallback_title
        
        # 最后回退到 <title> 标签
        title_node = parser.css("title")
        if title_node:
            title = title_node[0].text(strip=True)
            # 清理常见的网站后缀
            for suffix in ["-", "|", "_"]:
                if suffix in title:
                    title = title.split(suffix)[0].strip()
            if not ContentExtractor._is_nav_title(title):
                return title
        
        return fallback_title
    
    @staticmethod
    def _is_nav_title(title: str) -> bool:
        """
        判断是否是导航标题（非实际文章标题）
        
        避免提取类似「组织架构」「关于我们」等导航文本
        """
        nav_keywords = [
            "组织架构", "关于我们", "联系方式", "公司简介", "企业文化",
            "发展历程", "荣誉资质", "首页", "导航", "菜单", "网站地图",
            "新闻中心", "新闻列表", "公司新闻", "行业动态", "媒体报道"
        ]
        
        title_lower = title.lower().strip()
        
        # 太短的标题可能是导航
        if len(title) <= 2:
            return True
        
        # 检查是否包含导航关键词（完全匹配）
        for keyword in nav_keywords:
            if title == keyword or title_lower == keyword.lower():
                return True
        
        return False
    
    @staticmethod
    def _extract_publish_date(html: str, fallback_date: Optional[str] = None) -> Optional[str]:
        """
        提取发布日期
        
        Args:
            html: HTML 内容
            fallback_date: 回退日期（来自列表页）
        
        Returns:
            ISO 格式日期字符串，或 None
        """
        parser = HTMLParser(html)
        
        # 尝试查找日期相关元素
        date_selectors = [
            "time[datetime]",
            ".publish-time", ".pub-time", ".date", ".time",
            "[class*='date']", "[class*='time']",
            "[id*='date']", "[id*='time']",
            "h5", "h6", "span.meta"
        ]
        
        for selector in date_selectors:
            nodes = parser.css(selector)
            for node in nodes:
                # 尝试 datetime 属性
                datetime_attr = node.attributes.get("datetime")
                if datetime_attr:
                    normalized = ContentExtractor._normalize_date_text(datetime_attr)
                    if normalized:
                        return normalized
                
                # 尝试文本内容（包括 Ping An 风格的裸 h5 标签）
                text = node.text(strip=True)
                normalized = ContentExtractor._normalize_date_text(text)
                if normalized:
                    return normalized
        
        # 如果有列表页提供的日期，作为回退
        if fallback_date:
            return fallback_date
        
        return None
    
    @staticmethod
    def _normalize_date_text(text: str) -> Optional[str]:
        """
        从文本中提取并规范化日期
        
        支持格式:
        - YYYY-MM-DD
        - YYYY/MM/DD
        - YYYY年M月D日
        """
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

    # ------------------------------------------------------------ 服务化入口
    # 以下为「雷达新闻知识库写链路」（gd25 news_content_worker）新增：
    # 原地服务化，不移植代码 —— 抽取器只有这一份实现。

    @staticmethod
    def compute_content_hash(content: Optional[str]) -> Optional[str]:
        """
        计算正文哈希：空白归一后取 **sha1**（十六进制，40 字符）。

        ⚠️ 与 `models.ArticleRecord.compute_content_hash` 的差别只在摘要算法：
        那边是 sha256（64 字符，供文件/接口用），这边是 sha1 —— 因为
        exhibition `radar_company_news_document.content_hash` 是 `char(40)`。
        归一化口径（`" ".join(content.split())`）两者一致，勿改。

        Args:
            content: 正文；空则返回 None

        Returns:
            sha1 十六进制串，或 None
        """
        if not content:
            return None
        normalized = " ".join(str(content).split())
        if not normalized:
            return None
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def extract_article(
        html: str,
        url: str,
        list_title: Optional[str] = None,
        list_date: Optional[str] = None,
        summary_max_length: int = 200,
    ) -> ExtractedArticle:
        """
        抽取一篇详情页文章并补齐知识库所需字段（worker 直接调用）。

        与 `extract()` 共用同一套抽取逻辑（trafilatura 主 + selectolax 回退），
        只是把输出补成 `ExtractedArticle`：多生成 200 字摘要与 sha1 正文哈希。

        Args:
            html: 详情页 HTML
            url: 详情页 URL
            list_title: 列表页标题（回退用，任务表快照里没有时为 None）
            list_date: 列表页日期（回退用）
            summary_max_length: 摘要字数（默认 200）

        Returns:
            ExtractedArticle（正文可能为 None，由调用方按 min_chars 判定成败）
        """
        title, published_at, content = ContentExtractor.extract(
            html, url, list_title=list_title, list_date=list_date
        )
        return ExtractedArticle(
            url=url,
            title=(title or "").strip() or None,
            published_at=(published_at or "").strip() or None,
            content_text=content,
            content_summary=ContentExtractor.generate_summary(
                content or "", max_length=summary_max_length
            ),
            content_hash=ContentExtractor.compute_content_hash(content),
        )
