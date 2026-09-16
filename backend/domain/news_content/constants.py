"""
雷达新闻知识库写入链路的常量与枚举语义。

⚠️ 数值必须与 exhibition 侧严格一致（DDL 见
`projectDocs/技术设计文档-0905/SQL脚本/17_radar_news_content_schema.sql`）：

    radar_news_content_task.status       0 PENDING / 1 RUNNING / 2 SUCCESS / 3 FAILED
    radar_company_news_document.fetch_status   0 未抓 / 1 已抓 / 2 失败
    radar_company_news_document.embed_status   0 待向量化 / 1 已向量化 / 2 失败

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md` §4.1 / §4.2
"""
from __future__ import annotations

# ---------------------------------------------------------------- task 表
TASK_STATUS_PENDING = 0
TASK_STATUS_RUNNING = 1
TASK_STATUS_SUCCESS = 2
TASK_STATUS_FAILED = 3

TASK_STATUS_TEXT = {
    TASK_STATUS_PENDING: "PENDING",
    TASK_STATUS_RUNNING: "RUNNING",
    TASK_STATUS_SUCCESS: "SUCCESS",
    TASK_STATUS_FAILED: "FAILED",
}

# `actual_channel` / `source_type` 取值（结果字段，非调度字段）
CHANNEL_RULE = "rule"
CHANNEL_AGENT = "agent"

# ---------------------------------------------------------------- document 表
FETCH_STATUS_PENDING = 0
FETCH_STATUS_OK = 1
FETCH_STATUS_FAILED = 2

EMBED_STATUS_PENDING = 0
EMBED_STATUS_OK = 1
EMBED_STATUS_FAILED = 2
