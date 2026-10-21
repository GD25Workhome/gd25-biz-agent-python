"""
规则二 v3 事件决策（M6）。

目标：同一商机只保留一条代表行；只插、不更、不关；独立新需求单独成条。
聚合键 = (space_object, place, procurement_scope)（同主体 company_id 下）。
设计：华院Agent设计/02-技术设计/02-评分、自检与落库规则.md §3。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.app.api.schemas.huayuan_radar_event import RadarEventScoreResult

INSERT = "INSERT"
UPDATE = "UPDATE"  # 已停用（261019）：不再更新既有事件；见 decide_action 说明
NOOP = "NOOP"


@dataclass
class EventDecision:
    """事件决策结果。"""

    action: str  # INSERT | NOOP
    event_id: Optional[int] = None  # 命中的既有事件 id（供审计；不落库时也带）
    reason: str = ""
    parent_event_id: Optional[int] = None  # 插入时的父事件（同一商机的根）


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


def _as_bool(value: Any) -> bool:
    """history 布尔值兼容：True/1/b'\\x01' → True。"""
    if isinstance(value, (bytes, bytearray)):
        return any(value)
    if isinstance(value, str):
        return value not in ("", "0", "false", "False", "None", "none")
    return bool(value)


def _is_published(row: dict[str, Any]) -> bool:
    """该既有事件是否已发布（`radar_event.published=1`；发布后可撤回）。"""
    return _as_bool(row.get("published"))


def _is_closed(row: dict[str, Any]) -> bool:
    """该既有事件/商机是否已关闭或失效（不复活）。"""
    # 族内聚合（prepare 分组时按"或"算好）
    if _as_bool(row.get("closed")):
        return True
    if _as_bool(row.get("expired_or_done")):
        return True
    if str(row.get("validity_status") or "").strip().upper() in {"EXPIRED", "INVALID"}:
        return True
    # 商机层：关闭 / 已签署（radar_opportunity.status）
    return str(row.get("opportunity_status") or "").strip().lower() in {"closed", "signed"}


def _find_by_id(history: list[dict[str, Any]], event_id: Any) -> Optional[dict[str, Any]]:
    """在 history（已限本企业）里按 id 找一条。"""
    try:
        target = int(event_id)
    except (TypeError, ValueError):
        return None
    for row in history:
        try:
            if int(row.get("id") or 0) == target:
                return row
        except (TypeError, ValueError):
            continue
    return None


def _resolve_target(
    score: RadarEventScoreResult, history: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """
        找本次对应的既有商机（代表行）。

        优先级：① Agent 指认 `matched_event_id`（须∈本企业 history）；② 文本键兜底匹配。

        Args:
            score: 本次评分
            history: 该企业历史事件摘要（已按族去重）

        Returns:
            命中的代表行；无则 None
    """
    if score.matched_event_id is not None:
        hit = _find_by_id(history, score.matched_event_id)
        if hit is not None:
            return hit
    candidates = match_existing_events(score, history)
    if not candidates:
        return None
    return _pick_primary(candidates)


def decide_action(
    score: RadarEventScoreResult, history: list[dict[str, Any]]
) -> EventDecision:
    """
        判断本次评分应对事件表做什么（**只插、不更、不关**，261019 定稿）。

        Args:
            score: 本次评分（已过自检）
            history: 该企业历史事件摘要（已按商机族去重、每组一条）

        Returns:
            EventDecision

        规则：
            - 与展厅无关 → NOOP（不动既有）
            - 已完成/失效（`expired_or_done`）→ NOOP（不落库，也不写关闭）
            - 无匹配历史 → INSERT（新商机，`parent_event_id = NULL` = 根）
            - 命中既有商机：
                · 已发布（`published=1`）→ NOOP（**不落库**）
                · 已关闭/失效/已签署（`closed` / `opportunity_status ∈ {closed,signed}`）→ NOOP（**不落库**，不复活）
                · 未发布未关闭 → **INSERT**（按新建处理；`parent_event_id` = 族根 `root_event_id`）

        说明：UPDATE 已停用——不再覆盖既有事件（避免把 `published` / `verify_status` 抹掉）。
    """
    if not score.exhibition_related:
        return EventDecision(action=NOOP, reason="本次与展厅无关，不新建/不覆盖")
    if score.expired_or_done:
        # 已完成/失效 → 不落库、也不写关闭（只插不关）
        return EventDecision(action=NOOP, reason="本次判定已完成/失效：不落库（只插不关）")

    target = _resolve_target(score, history)
    if target is None:
        return EventDecision(action=INSERT, reason="无匹配历史，新建事件（根）")

    primary_id = target.get("id")

    if _is_published(target):
        return EventDecision(
            action=NOOP, event_id=primary_id, reason="命中已发布商机，不落库"
        )
    if _is_closed(target):
        return EventDecision(
            action=NOOP,
            event_id=primary_id,
            reason="命中已关闭/失效商机，不落库（不复活）",
        )
    # 未发布、未关闭 → 按新建插入，挂到族根（同一商机的时间线）
    root_id = target.get("root_event_id") or primary_id
    return EventDecision(
        action=INSERT,
        event_id=primary_id,
        parent_event_id=int(root_id) if root_id is not None else None,
        reason="命中未发布未关闭商机：按新建插入（挂根）",
    )