"""
新闻 URL Agent 抓取接口的请求与响应模型。

对接 exhibition：POST /api/v1/huayuan/news-url-crawl
设计文档：华院Agent设计/260914-整体重构/02-gd25侧详细设计.md §3.2
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl

# 停止原因枚举（见 02 §3.3）
StopReason = Literal[
    "hit_known",        # 命中 known_urls，主动停止翻页
    "max_pages",        # 达到 max_pages 上限
    "no_next",          # 找不到后续列表页（到末页）
    "no_detail_links",  # 列表页抓到了但抽不到详情链接 → 通道问题信号
]

# known_urls 上限：实验单站最大 174 条，给 500 足够宽松并防滥用
MAX_KNOWN_URLS = 500

# max_pages 上限：实验最多 8 页；20 页单次成本可能 $2+
MAX_PAGES_LIMIT = 20


class NewsUrlCrawlRequest(BaseModel):
    """新闻 URL 抓取请求。"""

    news_list_url: HttpUrl = Field(..., description="新闻列表入口页 URL")

    known_urls: List[str] = Field(
        default_factory=list,
        max_length=MAX_KNOWN_URLS,
        description=(
            "上一次已抓取的新闻详情 URL 清单。"
            "Agent 据此判断是否已翻到历史区域；返回结果也会减去这些 URL。"
            "传空数组表示首次抓取（全量）。"
        ),
    )

    company_name: Optional[str] = Field(
        None, max_length=255, description="企业名称，辅助站点消歧"
    )
    stock_code: Optional[str] = Field(
        None, max_length=16, description="证券代码，辅助站点消歧"
    )
    max_pages: int = Field(
        8, ge=1, le=MAX_PAGES_LIMIT, description="列表页抓取上限"
    )
    trace_id: Optional[str] = Field(
        None, max_length=64, description="链路追踪 ID，便于双边日志串联"
    )


class NewsUrlItem(BaseModel):
    """单条新闻详情 URL。"""

    url: str
    title: str = ""
    published_at: Optional[str] = None


class NewsUrlCrawlStats(BaseModel):
    """执行统计。"""

    candidate_count: int = Field(
        0, description="Agent 在列表页上识别出的候选总数（含 known_urls）"
    )
    known_hit_count: int = Field(0, description="命中 known_urls 的条数")
    list_page_urls: List[str] = Field(
        default_factory=list, description="实际抓取的列表页 URL（按顺序）"
    )
    agent_turns: Optional[int] = Field(None, description="Agent 轮次")
    agent_cost_usd: Optional[float] = Field(None, description="Agent 成本（美元）")
    duration_ms: Optional[int] = Field(None, description="耗时（毫秒）")


class NewsUrlCrawlResponse(BaseModel):
    """新闻 URL 抓取响应。"""

    news_urls: List[NewsUrlItem] = Field(
        default_factory=list,
        description="只含 known_urls 之外的新闻详情 URL",
    )
    list_pages_fetched: int = Field(0, description="实际抓取的列表页数")
    stop_reason: StopReason = Field("no_next", description="停止原因")
    stats: NewsUrlCrawlStats = Field(default_factory=NewsUrlCrawlStats)
    trace_id: Optional[str] = Field(None, description="本次请求的追踪 ID")
