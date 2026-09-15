"""
新闻 URL 抓取领域异常。

设计文档：华院Agent设计/260914-整体重构/02-gd25侧详细设计.md §3.4
"""
from __future__ import annotations


class NewsCrawlError(Exception):
    """新闻抓取基类异常。"""


class ListFetchError(NewsCrawlError):
    """列表页全部抓取失败（网络 / 反爬 / 通道问题）。"""


class AgentExecutionError(NewsCrawlError):
    """Agent 本身执行失败（SDK 异常、is_error=true、CLI 不可用）。"""
