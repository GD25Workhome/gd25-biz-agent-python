"""
采集阶段招采截止日过滤：已过期或两周内到期的证据不得计入事件信号。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.domain.flows.implementations.radar_evidence_gather_node import (
    drop_closed_procurement_briefs,
    parse_procurement_deadline,
    procurement_deadline_block_reason,
)

_TODAY = date(2026, 9, 28)


def test_parse_chinese_and_iso_deadline() -> None:
    """中文日期与 ISO 日期都能落到截止标签后面。"""
    assert parse_procurement_deadline("投标截止时间：2026年12月1日09时30分") == date(2026, 12, 1)
    assert parse_procurement_deadline("报名截止日期: 2026-12-01") == date(2026, 12, 1)
    assert parse_procurement_deadline("开标时间 2026/12/01 09:30") == date(2026, 12, 1)


def test_date_before_kaibiao_counts() -> None:
    """「某日开标」标签在日期后面时仍要识别。"""
    assert parse_procurement_deadline("定于2026年12月1日开标") == date(2026, 12, 1)


def test_publish_date_alone_is_not_deadline() -> None:
    """发布日不是招采窗口，不能据此丢掉证据。"""
    text = "发布日期：2024-01-01。该公司计划建设企业展厅。"
    assert parse_procurement_deadline(text) is None


def test_extension_overrides_original_deadline() -> None:
    """延期后的截止日优先于原文截止日。"""
    text = "投标截止时间：2026-01-01，后延期至2026-12-20"
    assert parse_procurement_deadline(text) == date(2026, 12, 20)


def test_past_deadline_is_dropped() -> None:
    """今天已经晚于截止日时，证据进入 discarded。"""
    briefs = [
        {
            "title": "展厅采购公告",
            "url": "https://ex.com/a",
            "summary": "投标截止时间：2026-09-01",
            "quote": None,
        }
    ]
    discarded: list = []
    drop_closed_procurement_briefs(briefs, discarded, today=_TODAY)
    assert briefs == []
    assert discarded[0]["reason"] == "招采截止日已过：2026-09-01"


def test_deadline_within_14_days_is_dropped() -> None:
    """距截止日不足 14 天（含第 14 天）不得计入信号。"""
    near = {
        "title": "临近",
        "url": "https://ex.com/near",
        "summary": "响应截止时间：2026-10-12",
        "quote": None,
    }
    edge = {
        "title": "刚好两周",
        "url": "https://ex.com/edge",
        "summary": "递交截止日期：2026-10-12",
        "quote": None,
    }
    # 2026-09-28 + 14 天 = 2026-10-12
    assert procurement_deadline_block_reason(near, _TODAY) is not None
    briefs = [near, edge]
    discarded: list = []
    drop_closed_procurement_briefs(briefs, discarded, today=_TODAY)
    assert briefs == []
    assert all("临近" in item["reason"] for item in discarded)


def test_deadline_beyond_14_days_is_kept() -> None:
    """窗口还剩 15 天以上的公告可以留下。"""
    kept = {
        "title": "仍有窗口",
        "url": "https://ex.com/ok",
        "summary": "投标截止时间：2026-10-13",
        "quote": None,
    }
    briefs = [kept]
    discarded: list = []
    drop_closed_procurement_briefs(briefs, discarded, today=_TODAY)
    assert briefs == [kept]
    assert discarded == []


def test_deadline_in_quote_is_scanned() -> None:
    """摘要没写截止日、正文摘录写了，也要忽略。"""
    briefs = [
        {
            "title": "展厅招标",
            "url": "https://ex.com/q",
            "summary": "见正文",
            "quote": "开标时间：2026年9月20日",
        }
    ]
    discarded: list = []
    drop_closed_procurement_briefs(briefs, discarded, today=_TODAY)
    assert briefs == []
    assert "2026-09-20" in discarded[0]["reason"]


def test_unparseable_notice_is_kept() -> None:
    """没有可解析截止日时不在采集阶段丢弃，交给终评判断。"""
    briefs = [
        {
            "title": "展厅建设意向",
            "url": "https://ex.com/intent",
            "summary": "计划新建企业展厅，尚未发布招标。",
            "quote": None,
        }
    ]
    discarded: list = []
    drop_closed_procurement_briefs(briefs, discarded, today=_TODAY)
    assert len(briefs) == 1
    assert discarded == []
