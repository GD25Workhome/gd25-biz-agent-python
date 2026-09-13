"""
数据模型定义
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum
import hashlib


@dataclass
class ListItem:
    """列表页提取的单条新闻项"""
    url: str
    title: Optional[str] = None
    published_at: Optional[str] = None


class SiteType(str, Enum):
    """站点类型枚举"""
    STATIC = "static"
    CMS = "cms"
    SPA = "spa"
    API = "api"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class FetchMethod(str, Enum):
    """抓取方法枚举"""
    HTTP = "http"
    BROWSER = "browser"


class SourceLevel(str, Enum):
    """来源级别枚举"""
    P0_OFFICIAL_SITE = "P0_official_site"


@dataclass
class SiteProfile:
    """站点配置档案"""
    stock_code: str
    company_name: str
    list_url: str
    site_type: SiteType = SiteType.UNKNOWN
    last_http_status: Optional[int] = None
    last_article_link_count: int = 0
    last_success_at: Optional[datetime] = None
    fail_streak: int = 0
    notes: str = ""
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "stock_code": self.stock_code,
            "company_name": self.company_name,
            "list_url": self.list_url,
            "site_type": self.site_type.value,
            "last_http_status": self.last_http_status,
            "last_article_link_count": self.last_article_link_count,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "fail_streak": self.fail_streak,
            "notes": self.notes,
        }


@dataclass
class ArticleRecord:
    """文章记录"""
    stock_code: str
    company_name: str
    source_level: SourceLevel
    list_url: str
    article_url: str
    url_norm: str
    title: str
    published_at: Optional[str]
    fetched_at: datetime
    content_text: str
    content_hash: str
    summary: str
    http_status: int
    fetch_method: FetchMethod
    template_id: str
    site_type: SiteType
    parse_version: str = "company_news_mvp_v1"
    
    @staticmethod
    def compute_content_hash(content: str) -> str:
        """计算内容哈希"""
        normalized = " ".join(content.split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "stock_code": self.stock_code,
            "company_name": self.company_name,
            "source_level": self.source_level.value,
            "list_url": self.list_url,
            "article_url": self.article_url,
            "url_norm": self.url_norm,
            "title": self.title,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at.isoformat(),
            "content_text": self.content_text,
            "content_hash": self.content_hash,
            "summary": self.summary,
            "http_status": self.http_status,
            "fetch_method": self.fetch_method.value,
            "template_id": self.template_id,
            "site_type": self.site_type.value,
            "parse_version": self.parse_version,
        }


@dataclass
class CrawlResult:
    """爬取结果"""
    profile: SiteProfile
    articles: List[ArticleRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "profile": self.profile.to_dict(),
            "articles": [a.to_dict() for a in self.articles],
            "errors": self.errors,
        }
