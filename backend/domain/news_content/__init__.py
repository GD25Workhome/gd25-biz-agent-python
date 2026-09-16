"""
雷达新闻知识库写链路领域模块（gd25 常驻 worker 侧）。

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md`

模块划分
    constants.py        状态/通道常量（数值与 exhibition DDL 严格对齐）
    repository.py       两张表的 SQL（radar_news_content_task / radar_company_news_document）
    rate_limiter.py     同站最小间隔限速
    content_fetcher.py  规则版详情页抓取（复用 company_news_crawl 的抽取器）
    agent_fallback.py   规则失败后的 Agent 兜底（日配额 + 熔断）
    pipeline.py         单任务编排 + 补跑循环
    worker_loop.py      扫表抢锁主循环（CLI 与 FastAPI lifespan 共用）

⚠️ `__init__` 刻意保持轻量：不在这里 import pipeline/agent_fallback，
避免「只想读常量却拉起 pymilvus / claude_agent_sdk」的副作用。
入口请按需 import 子模块，例如：
    from backend.domain.news_content.pipeline import NewsContentProcessor
"""
from backend.domain.news_content.constants import (
    CHANNEL_AGENT,
    CHANNEL_RULE,
    EMBED_STATUS_FAILED,
    EMBED_STATUS_OK,
    EMBED_STATUS_PENDING,
    FETCH_STATUS_FAILED,
    FETCH_STATUS_OK,
    FETCH_STATUS_PENDING,
    TASK_STATUS_FAILED,
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SUCCESS,
)

__all__ = [
    "TASK_STATUS_PENDING",
    "TASK_STATUS_RUNNING",
    "TASK_STATUS_SUCCESS",
    "TASK_STATUS_FAILED",
    "FETCH_STATUS_PENDING",
    "FETCH_STATUS_OK",
    "FETCH_STATUS_FAILED",
    "EMBED_STATUS_PENDING",
    "EMBED_STATUS_OK",
    "EMBED_STATUS_FAILED",
    "CHANNEL_RULE",
    "CHANNEL_AGENT",
]
