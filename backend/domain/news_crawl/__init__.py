"""
新闻 URL 抓取领域模块。

设计文档：华院Agent设计/260914-整体重构/02-gd25侧详细设计.md

⚠️ 本包不依赖任何数据库模块 —— 接口无状态，ENABLE_DATABASE=false 下可正常工作。
"""
from backend.domain.news_crawl.exceptions import (
    AgentExecutionError,
    ListFetchError,
    NewsCrawlError,
)
from backend.domain.news_crawl.url_norm import normalize, normalize_many

__all__ = [
    "NewsCrawlError",
    "ListFetchError",
    "AgentExecutionError",
    "normalize",
    "normalize_many",
]
