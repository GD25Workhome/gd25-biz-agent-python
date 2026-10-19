"""
M6 事件更新决策（event_update.py）单元测试：矩阵 A–F。
"""
from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.app.api.schemas.huayuan_radar_event import RadarEventScoreResult
from radar_score.event_update import (
    INSERT,
    NOOP,
    UPDATE,
    decide_action,
    match_existing_events,
)


def _score(
    *,
    space_object="展示中心",
    place="上海",
    procurement_scope="intent_phase",
    expired=False,
    related=True,
) -> RadarEventScoreResult:
    return RadarEventScoreResult(
        exhibition_related=related,
        signal_summary="x",
        space_object=space_object,
        place=place,
        procurement_scope=procurement_scope,
        expired_or_done=expired,
    )


def _hist(*, id, space_object="展示中心", place="上海", procurement_scope="intent_phase",
          expired=False, total=70):
    return {
        "id": id,
        "space_object": space_object,
        "place": place,
        "procurement_scope": procurement_scope,
        "expired_or_done": expired,
        "total_score": total,
        "system_level": "S2",
        "update_time": "2026-09-01 00:00:00",
    }


def test_d_no_match_insert() -> None:
    """D：无匹配 → INSERT。"""
    d = decide_action(_score(), [])
    assert d.action == INSERT


def test_a_same_key_advance_update() -> None:
    """A：同键有效 + 本次有效 → UPDATE 原事件。"""
    d = decide_action(_score(), [_hist(id=11)])
    assert d.action == UPDATE
    assert d.event_id == 11


def test_b_closed_not_revived() -> None:
    """B：同键原事件已完成/失效 → NOOP（不复活）。"""
    d = decide_action(_score(), [_hist(id=12, expired=True)])
    assert d.action == NOOP
    assert d.event_id == 12


def test_f_active_closed_by_expired_run() -> None:
    """F：同键原事件有效 + 本次判定失效 → UPDATE（关闭）。"""
    d = decide_action(_score(expired=True), [_hist(id=13)])
    assert d.action == UPDATE
    assert d.event_id == 13


def test_reject_unrelated_noop() -> None:
    """与展厅无关 → NOOP，不新建/不覆盖。"""
    d = decide_action(_score(related=False), [_hist(id=14)])
    assert d.action == NOOP


def test_expired_with_no_history_inserts_history_record() -> None:
    """已完成/失效且首次发现 → INSERT（沉淀历史）。"""
    d = decide_action(_score(expired=True), [])
    assert d.action == INSERT


def test_e_multiple_candidates_pick_active_high_score() -> None:
    """E：多个同键 → 选未失效且总分高者。"""
    hist = [
        _hist(id=21, expired=True, total=90),
        _hist(id=22, expired=False, total=60),
        _hist(id=23, expired=False, total=75),
    ]
    d = decide_action(_score(), hist)
    assert d.action == UPDATE
    assert d.event_id == 23


def test_different_key_not_matched() -> None:
    """不同地点/对象 → 不匹配（独立新需求）。"""
    d = decide_action(_score(place="北京"), [_hist(id=31, place="上海")])
    assert d.action == INSERT


def test_empty_space_object_no_match() -> None:
    """展厅对象为空 → 不匹配（避免误并）。"""
    matched = match_existing_events(_score(space_object=""), [_hist(id=41)])
    assert matched == []
    assert decide_action(_score(space_object=""), [_hist(id=41)]).action == INSERT