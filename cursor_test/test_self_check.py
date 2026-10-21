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
from radar_score.rules import validity
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

# ---------------- R7 时效闸门 / R9 日期纪律（裁定 D7/D8/D9 + radar_score/rules）----------------

from datetime import date  # noqa: E402


def _score_v3(
    *,
    signal_time: str | None = "2026-09-01",
    fact_time: str | None = None,
    fact_ev_no: int | None = None,
    publish_dates: tuple[str, ...] = ("2026-06-01",),
    evidence: int | None = 75,
    specificity: int | None = 10,
) -> RadarEventScoreResult:
    """构造带时间字段的评分结果（每条证据一个 evidence_no）。"""
    evidences = [
        RadarEventEvidenceItem(
            evidence_no=i,
            source_type="web",
            url=f"https://ex.com/{i}",
            kept=True,
            publish_date=(pd or None),
        )
        for i, pd in enumerate(publish_dates)
    ]
    total = None if evidence is None or specificity is None else evidence + specificity
    return RadarEventScoreResult(
        exhibition_related=True,
        signal_summary="公告披露展示中心建设",
        signal_time=signal_time,
        fact_time_earliest=fact_time,
        fact_time_earliest_evidence_no=fact_ev_no,
        evidence_score=evidence,
        specificity_score=specificity,
        total_score=total,
        evidences=evidences,
    )


def test_validity_floor_is_rolling_window() -> None:
    """窗口＝评估日往回 12 个月（滚动）；边界按天判定，年月精度取月初（保守）。"""
    today = date(2026, 10, 20)
    assert validity.validity_floor(today).isoformat() == "2025-10-20"
    assert validity.is_within_validity("2025-10-20", today)[0] is True    # 正好下界
    assert validity.is_within_validity("2025-10-19", today)[0] is False   # 早 1 天
    assert validity.is_within_validity("2024-10-19", today)[0] is False   # 约 24 个月
    assert validity.is_within_validity("2025-10", today)[0] is False      # → 2025-10-01
    assert validity.is_within_validity("2026-04", today)[0] is True
    assert validity.validity_floor(date(2026, 3, 31)).isoformat() == "2025-03-31"


def test_is_run_date_stamp() -> None:
    """跑批日戳判定（D7）。"""
    run = date(2026, 10, 20)
    assert validity.is_run_date_stamp("2026-10-20", run) is True
    assert validity.is_run_date_stamp("2026-10-19", run) is False
    assert validity.is_run_date_stamp(None, run) is False
    assert validity.is_run_date_stamp("近期", run) is False


def test_r7_expires_when_earliest_fact_out_of_window() -> None:
    """R7：最早事实 2024-03（5333 情形）→ 判 expired、两维分与总分置 null。"""
    score = _score_v3(fact_time="2024-03-14", fact_ev_no=0, signal_time="2025-11-14")
    out = check(score, today=date(2026, 10, 20))
    assert out.ok is True and out.level_final is None
    assert score.expired_or_done is True
    assert score.admission_hint == "expired"
    assert score.total_score is None and score.evidence_score is None
    assert any("R7" in n for n in out.notes)


def test_r7_keeps_in_window_event() -> None:
    """R7：最早事实在窗内 → 不判 expired，等级照常。"""
    score = _score_v3(fact_time="2026-04-10", fact_ev_no=0, signal_time="2025-11-14")
    out = check(score, today=date(2026, 10, 20))
    assert score.expired_or_done is False
    assert out.level_final == "S1"


def test_r7_falls_back_to_signal_time() -> None:
    """R7：缺 fact_time_earliest 时回落 signal_time，并在 note 标注回落。"""
    score = _score_v3(fact_time=None, signal_time="2024-01-05")
    out = check(score, today=date(2026, 10, 20))
    assert score.expired_or_done is True
    assert any("signal_time(回落)" in n for n in out.notes)


def test_r7_unparsable_time_not_killed_by_code() -> None:
    """R7：时间读不出来 → 不判死（交语义复核），仍给分。"""
    score = _score_v3(fact_time="近期", signal_time=None)
    out = check(score, today=date(2026, 10, 20))
    assert score.expired_or_done is False
    assert out.level_final == "S1"
    assert any("无法解析" in n for n in out.notes)


def test_r9_drops_run_date_stamp_evidence() -> None:
    """R9：publish_date == 跑批日 → 只剔除那一条并留痕，不整体判失败。"""
    score = _score_v3(publish_dates=("2026-10-20", "2026-06-01"))
    out = check(score, today=date(2026, 10, 20))
    assert out.ok is True
    assert out.dropped_evidence_nos == [0]
    assert score.evidences[0].kept is False
    assert score.evidences[1].kept is True
    assert any("R9" in n for n in out.notes)


def test_r9_dropping_only_valid_evidence_triggers_r2() -> None:
    """R9 把唯一证据剔除后 → R2「有分必有据」生效（ok=False）。"""
    score = _score_v3(publish_dates=("2026-10-20",))
    out = check(score, today=date(2026, 10, 20))
    assert out.ok is False
    assert out.dropped_evidence_nos == [0]


# ---------------- R9 来源抑制表（D7：行情/聚合页）----------------

from radar_score.rules import sources  # noqa: E402


def test_suppressed_source_table() -> None:
    """抑制表只打行情/列表/聚合页；问答/公告/官网不抑制。"""
    assert sources.is_suppressed_url("https://www.stcn.com/quotes/index/bj920180.html")[0] is True
    assert sources.is_suppressed_url("https://quote.eastmoney.com/sz300302.html")[0] is True
    assert sources.is_suppressed_url("http://finance.sina.com.cn/realstock/company/sz000001/nc.shtml")[0] is True
    # 不抑制：互动问答（5333 的 e1 就是这类，带公司答复）、公告 PDF、官网
    assert sources.is_suppressed_url("https://ir.p5w.net/question/5d5c54829a0644938f5ad03d0e46a0eb.shtml")[0] is False
    assert sources.is_suppressed_url("http://static.cninfo.com.cn/finalpage/2026-04-10/1225096525.PDF")[0] is False
    assert sources.is_suppressed_url("https://www.haohua.com/about")[0] is False
    assert sources.is_suppressed_url(None)[0] is False


def test_r9_drops_suppressed_market_page() -> None:
    """R9：行情页证据被剔除并留痕（只剔那一条，不整体判失败）。"""
    score = _score_v3(publish_dates=("2026-06-01", "2026-06-02"))
    score.evidences[0].url = "https://www.stcn.com/quotes/index/bj920180.html"
    out = check(score, today=date(2026, 10, 20))
    assert out.ok is True
    assert out.dropped_evidence_nos == [0]
    assert score.evidences[1].kept is True
    assert any("行情" in n for n in out.notes)


# ---------------- 基准交叉校验（D8 补口：模型不能自选"晚发布材料"当时效基准）----------------

def test_r7_basis_conflict_holds_instead_of_overriding() -> None:
    """5333 情形：模型把基准填成 2025-11 重申稿、证据里有 2024-03 立项公告 → **不改判、挂起待核验**。

    代码只能发现矛盾（候选无法判断是否同簇，自动改判会误杀 ~69%），定夺交 auditor / 人工。
    """
    score = _score_v3(
        fact_time="2025-11-14", fact_ev_no=1, signal_time="2026-01-23",
        publish_dates=("2025-11-14", "2024-03-14"),
    )
    score.admission_hint = "pass"
    score.evidences[1].quote = "在张家港总部建设培训中心和展厅…已取得投资项目备案证"
    out = check(score, today=date(2026, 10, 20))
    assert score.fact_time_earliest == "2025-11-14"      # 基准不被自动改写
    assert score.expired_or_done is False               # 不误杀
    assert score.admission_hint == "pending_verify"     # 挂起待核验
    assert any("基准存疑" in n for n in out.notes)


def test_r7_no_conflict_for_unrelated_old_page() -> None:
    """无关旧页（无展厅实体词）不构成矛盾：不挂起、维持 S1。"""
    score = _score_v3(
        fact_time="2026-04-10", signal_time="2026-04-10",
        publish_dates=("2026-04-10", "2010-06-01"),
    )
    score.evidences[1].title = "公司简介"
    score.evidences[1].quote = "成立于 2010 年，主营医疗器械"
    out = check(score, today=date(2026, 10, 20))
    assert score.fact_time_earliest == "2026-04-10"
    assert score.expired_or_done is False
    assert out.level_final == "S1"
    assert not any("基准存疑" in n for n in out.notes)


def test_r7_no_conflict_when_only_context_mention() -> None:
    """只"参观/汇报"语境提及展厅（无项目动作词）→ 不算项目事实 → 不挂起。"""
    score = _score_v3(
        fact_time="2026-06-01", signal_time="2026-06-01",
        publish_dates=("2026-06-01", "2022-05-06"),
    )
    score.evidences[1].quote = "带领来宾参观了公司展厅、生产线，并介绍了目前生产情况"
    out = check(score, today=date(2026, 10, 20))
    assert score.expired_or_done is False
    assert out.level_final == "S1"
    assert not any("基准存疑" in n for n in out.notes)


def test_r7_cross_check_tolerates_small_gap() -> None:
    """模型基准与证据候选接近（<183 天）→ 不挂起。"""
    score = _score_v3(fact_time="2026-06-01", signal_time="2026-06-01",
                      publish_dates=("2026-06-01", "2026-04-01"))
    score.evidences[1].quote = "展厅改造项目招标公告"
    out = check(score, today=date(2026, 10, 20))
    assert score.fact_time_earliest == "2026-06-01"
    assert score.expired_or_done is False
