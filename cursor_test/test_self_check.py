"""
radar_score/self_check（M5）单元测试：覆盖 R1–R6。
"""
from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.app.api.schemas.huayuan_radar_event import (
    RadarEventEvidenceItem,
    RadarEventScoreResult,
)
from radar_score.self_check import check, level_from_total


def _score(
    *,
    evidence: int | None,
    specificity: int | None,
    suggested: str | None = None,
    is_potential: bool = False,
    signal_category: str | None = None,
    with_evidence: bool = True,
) -> RadarEventScoreResult:
    """构造评分结果（默认带一条合法 kept 证据）。"""
    total = None
    if evidence is not None and specificity is not None:
        total = evidence + specificity
    evidences = []
    if with_evidence:
        evidences = [
            RadarEventEvidenceItem(
                evidence_no=0, source_type="web", url="https://ex.com/a", kept=True
            )
        ]
    return RadarEventScoreResult(
        exhibition_related=True,
        signal_summary="公告披露展示中心建设",
        signal_time="2026-09-01",
        evidence_score=evidence,
        specificity_score=specificity,
        total_score=total,
        suggested_level=suggested,
        is_potential=is_potential,
        signal_category=signal_category,
        evidences=evidences,
    )


def test_level_from_total() -> None:
    """区间映射：75/50/25 边界。"""
    assert level_from_total(85) == "S1"
    assert level_from_total(75) == "S1"
    assert level_from_total(74) == "S2"
    assert level_from_total(50) == "S2"
    assert level_from_total(49) == "S3"
    assert level_from_total(25) == "S3"
    assert level_from_total(24) == "S4"
    assert level_from_total(0) == "S4"
    assert level_from_total(None) is None


def test_r1_illegal_score_fails() -> None:
    """R1 非法档位（30）→ ok=False。"""
    out = check(_score(evidence=30, specificity=15))
    assert out.ok is False


def test_r1_legacy_score_tolerated() -> None:
    """R1 历史档 60 放过但记录 note。"""
    out = check(_score(evidence=60, specificity=10))
    assert out.ok is True
    assert any("R1" in n for n in out.notes)
    assert out.level_final == "S2"  # 70 → S2


def test_r2_has_score_without_evidence_fails() -> None:
    """R2 有分但无有效证据 → ok=False。"""
    out = check(_score(evidence=75, specificity=10, with_evidence=False))
    assert out.ok is False


def test_r3_suggested_level_conflict_uses_interval() -> None:
    """R3 建议 S1 但区间为 S3 → 以区间为准 + note。"""
    out = check(_score(evidence=25, specificity=15, suggested="S1"))
    assert out.ok is True
    assert out.level_final == "S3"
    assert any("R3" in n for n in out.notes)


def test_r5_fixed_s4_zero_tier() -> None:
    """R5 evidence=0 → 固定 S4，即便建议 S1。"""
    out = check(_score(evidence=0, specificity=15, suggested="S1"))
    assert out.ok is True
    assert out.level_final == "S4"


def test_r6_potential_capped_s3() -> None:
    """R6 潜在档（is_potential）+ 高分区间 → 上限 S3。"""
    out = check(_score(evidence=85, specificity=15, is_potential=True))
    assert out.ok is True
    assert out.level_final == "S3"


def test_normal_high_level_passes() -> None:
    """常规高分：85+10=95 → S1，无 cap。"""
    out = check(_score(evidence=85, specificity=10, suggested="S1"))
    assert out.ok is True
    assert out.level_final == "S1"
    assert out.cap_reason is None


def test_excluded_no_level() -> None:
    """不准入/失效 → 无等级，ok=True。"""
    score = _score(evidence=None, specificity=None)
    score.exhibition_related = False
    score.total_score = None
    out = check(score)
    assert out.ok is True
    assert out.level_final is None