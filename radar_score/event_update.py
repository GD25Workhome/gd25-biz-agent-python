"""
规则二 v3 事件更新决策（M6）。

目标：同一事件按新阶段推进/关闭，不重复生成商机；独立新需求单独成条。
聚合键 = (space_object, place, procurement_scope)（同主体 company_id 下）。
设计：华院Agent设计/261016-Agent重构/Agent整体设计/05-详细设计.md §7.1（矩阵 A–F）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.app.api.schemas.huayuan_radar_event import RadarEventScoreResult

INSERT = "INSERT"
UPDATE = "UPDATE"
NOOP = "NOOP"


@dataclass
class EventDecision:
    """事件更新决策结果。"""

    action: str  # INSERT | UPDATE | NOOP
    event_id: Optional[int] = None  # UPDATE 时的目标事件；NOOP 时指向既有事件（可空）
    reason: str = ""


def _norm(value: Any) -> str:
    """键归一化：去空白、小写。"""
    return str(value or "").strip().lower()


def _key(space_object: Any, place: Any, procurement_scope: Any) -> tuple[str, str, str]:
    return (_norm(space_object), _norm(place), _norm(procurement_scope))


def match_existing_events(
    score: RadarEventScoreResult, history: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
        按聚合键匹配历史事件（同主体已由 M2 按 company_id 过滤）。

        Args:
            score: 本次评分
            history: 该企业历史事件摘要

        Returns:
            同键历史事件列表
    """
    key = _key(score.space_object, score.place, score.procurement_scope)
    # 展厅对象为空时无法可靠匹配（避免把不同需求误并），直接视为无匹配
    if not key[0]:
        return []
    return [
        h
        for h in history
        if _key(h.get("space_object"), h.get("place"), h.get("procurement_scope")) == key
    ]


def _pick_primary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """从多个同键候选中挑主事件：优先未失效，其次总分高，最后取最新。"""
    def sort_key(item: dict[str, Any]):
        expired = bool(item.get("expired_or_done"))
        total = item.get("total_score") or 0
        # 未失效优先（False < True）；总分降序；history 已按 update_time 倒序
        return (expired, -int(total))

    return sorted(candidates, key=sort_key)[0]


def decide_action(
    score: RadarEventScoreResult, history: list[dict[str, Any]]
) -> EventDecision:
    """
        判断本次评分应对事件表做什么。

        Args:
            score: 本次评分（已过自检）
            history: 该企业历史事件摘要

        Returns:
            EventDecision

        规则（矩阵）：
            - 与展厅无关（reject）→ NOOP（不动既有）
            - 无同键历史 → INSERT（新需求 / 首次记录已完成历史）
            - 同键原事件已失效 → NOOP（不复活）
            - 同键原事件有效 + 本次失效 → UPDATE（关闭）
            - 同键原事件有效 + 本次有效 → UPDATE（推进/覆盖）
        """
    if not score.exhibition_related:
        return EventDecision(action=NOOP, reason="本次与展厅无关，不新建/不覆盖")

    candidates = match_existing_events(score, history)
    if not candidates:
        return EventDecision(action=INSERT, reason="无同键历史，新建事件")

    primary = _pick_primary(candidates)
    primary_id = primary.get("id")

    if primary.get("expired_or_done"):
        return EventDecision(
            action=NOOP,
            event_id=primary_id,
            reason="同范围原事件已完成/失效，不复活",
        )

    if score.expired_or_done:
        return EventDecision(
            action=UPDATE,
            event_id=primary_id,
            reason="本次判定失效，关闭原事件",
        )

    return EventDecision(
        action=UPDATE,
        event_id=primary_id,
        reason="同事件按当前阶段推进/覆盖",
    )