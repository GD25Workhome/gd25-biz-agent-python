"""
事件决策（radar_score/event_update.py）单元测试。

261019 定稿：**只插、不更、不关** —— 只有 INSERT，其余 NOOP（已发布/已关闭也不落库）。
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


def _hist(
    *,
    id,
    space_object="展示中心",
    place="上海",
    procurement_scope="intent_phase",
    expired=False,
    published=False,
    validity_status="ACTIVE",
    total=70,
    opportunity_status=None,
    root_event_id=None,
    closed=None,
):
    row = {
        "id": id,
        "space_object": space_object,
        "place": place,
        "procurement_scope": procurement_scope,
        "expired_or_done": expired,
        "published": published,
        "validity_status": validity_status,
        "total_score": total,
        "system_level": "S2",
        "update_time": "2026-09-01 00:00:00",
    }
    if opportunity_status is not None:
        row["opportunity_status"] = opportunity_status
    if root_event_id is not None:
        row["root_event_id"] = root_event_id
    if closed is not None:
        row["closed"] = closed
    return row


def test_no_match_insert() -> None:
    """无匹配 → INSERT。"""
    d = decide_action(_score(), [])
    assert d.action == INSERT


def test_matched_active_unpublished_insert() -> None:
    """同键有效 + 未发布未关闭 → 按新建 INSERT（有效数据，与新建同级）。"""
    d = decide_action(_score(), [_hist(id=11)])
    assert d.action == INSERT
    assert d.event_id == 11


def test_matched_published_noop() -> None:
    """同键已发布 → NOOP（不落库）。"""
    d = decide_action(_score(), [_hist(id=12, published=True)])
    assert d.action == NOOP
    assert d.event_id == 12


def test_matched_closed_noop() -> None:
    """同键已关闭/失效（validity_status=INVALID）→ NOOP（不复活）。"""
    d = decide_action(_score(), [_hist(id=13, validity_status="INVALID")])
    assert d.action == NOOP
    assert d.event_id == 13


def test_matched_expired_noop() -> None:
    """同键原事件已完成/失效 → NOOP（不复活）。"""
    d = decide_action(_score(), [_hist(id=14, expired=True)])
    assert d.action == NOOP
    assert d.event_id == 14


def test_active_closed_by_expired_run_noop() -> None:
    """同键原事件有效 + 本次判定失效 → 也不写关闭（只插不关）→ NOOP。"""
    d = decide_action(_score(expired=True), [_hist(id=15)])
    assert d.action == NOOP


def test_reject_unrelated_noop() -> None:
    """与展厅无关 → NOOP，不新建/不覆盖。"""
    d = decide_action(_score(related=False), [_hist(id=16)])
    assert d.action == NOOP


def test_expired_no_history_noop() -> None:
    """已完成/失效（含首次发现）→ 不落库（NOOP）。"""
    d = decide_action(_score(expired=True), [])
    assert d.action == NOOP


def test_multiple_candidates_pick_active_high_score() -> None:
    """多个同键 → 选未失效且总分高者（INSERT；event_id 指向它以示同一商机）。"""
    hist = [
        _hist(id=21, expired=True, total=90),
        _hist(id=22, expired=False, total=60),
        _hist(id=23, expired=False, total=75),
    ]
    d = decide_action(_score(), hist)
    assert d.action == INSERT
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


def test_agent_matched_event_id_wins() -> None:
    """Agent 指认 matched_event_id → 直接用该条（即使文本键不一致）。"""
    score = _score(space_object="展示中心", place="上海")
    score.matched_event_id = 77
    d = decide_action(score, [_hist(id=77, space_object="完全不同", place="别的")])
    assert d.action == INSERT
    assert d.parent_event_id == 77


def test_agent_matched_id_not_in_history_falls_back() -> None:
    """matched_event_id 不在 history（校验不过）→ 回退文本键；仍不匹配则按根新建。"""
    score = _score(place="北京")
    score.matched_event_id = 999
    d = decide_action(score, [_hist(id=81, place="上海")])
    assert d.action == INSERT
    assert d.parent_event_id is None


def test_insert_parent_is_root() -> None:
    """命中未发布未关闭 → INSERT 且 parent = 族根 root_event_id。"""
    d = decide_action(_score(), [_hist(id=80, root_event_id=70)])
    assert d.action == INSERT
    assert d.parent_event_id == 70


def test_opportunity_closed_noop() -> None:
    """商机 status=closed（退回）→ NOOP，不落库。"""
    d = decide_action(_score(), [_hist(id=78, opportunity_status="closed")])
    assert d.action == NOOP
    assert d.event_id == 78


def test_opportunity_signed_noop() -> None:
    """商机 status=signed（已签约）→ NOOP，不落库。"""
    d = decide_action(_score(), [_hist(id=79, opportunity_status="signed")])
    assert d.action == NOOP


def test_opportunity_suspended_not_blocked() -> None:
    """商机 status=suspended（撤回）→ 不算关闭，仍按新建插入。"""
    d = decide_action(_score(), [_hist(id=82, opportunity_status="suspended")])
    assert d.action == INSERT


def test_group_closed_flag_blocks_insert() -> None:
    """族内聚合 closed=True → NOOP（哪怕代表行自身未失效）。"""
    d = decide_action(_score(), [_hist(id=83, closed=True)])
    assert d.action == NOOP