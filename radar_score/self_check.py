"""
规则二 v3 落库前自检（M5）。

定位：把 v3 提示词产出的两维分与建议等级，做一层**代码硬边界兜底**，
防止 LLM 在分值区间边界上出现数学错误后把脏数据写进库。

设计：华院Agent设计/02-技术设计/02-评分、自检与落库规则.md §2。
注意：这是 3 行级防呆，**不是**还原 Java 规则包；档位语义全部由提示词承担。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from backend.app.api.schemas.huayuan_radar_event import (
    LEGACY_EVIDENCE_SCORES,
    VALID_EVIDENCE_SCORES,
    VALID_SPECIFICITY_SCORES,
    RadarEventScoreResult,
)
from radar_score.rules import sources, validity

# 等级由好到差排序，用于 capAtMost 取较差的一档
_LEVEL_RANK = {"S1": 1, "S2": 2, "S3": 3, "S4": 4}


@dataclass
class SelfCheckOutcome:
    """自检结果。"""

    ok: bool
    level_final: Optional[str]
    cap_reason: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    # R9 剔除的证据序号（图内/图外任一实现都要留痕，见 D7）
    dropped_evidence_nos: List[int] = field(default_factory=list)


def level_from_total(total: Optional[int]) -> Optional[str]:
    """
        按总分区间推导等级（v3 §3.5：75/50/25 分界线）。

        Args:
            total: 总分；None 表示不准入/失效

        Returns:
            S1–S4；total 为 None 时返回 None
    """
    if total is None:
        return None
    if total >= 75:
        return "S1"
    if total >= 50:
        return "S2"
    if total >= 25:
        return "S3"
    return "S4"


def _cap_at_most(level: Optional[str], max_level: str) -> Optional[str]:
    """把等级压到不优于 max_level（更好的一档压到 max_level；更差的保留）。"""
    if level is None:
        return None
    # rank 越小越好；level 比 max_level 更好 → 压到 max_level
    if _LEVEL_RANK.get(level, 99) < _LEVEL_RANK[max_level]:
        return max_level
    return level


def _has_valid_evidence(score: RadarEventScoreResult) -> bool:
    """kept 证据里是否至少有一条 web http url（有分必有据）。"""
    for ev in score.evidences:
        if not ev.kept:
            continue
        st = str(ev.source_type or "web").lower()
        if st == "web" and ev.url and str(ev.url).startswith("http"):
            return True
        if st == "knowledge_base" and str(ev.doc_id or "").strip():
            return True
    return False


def check(
    score: RadarEventScoreResult, *, today: Optional[date] = None
) -> SelfCheckOutcome:
    """
        对单条评分结果做落库前自检。

        Args:
            score: 已解析的评分结果（**会被就地修订**：R7 置 expired、R9 剔除证据）
            today: 评估日；None 取当前本地日期（便于单测注入）

        Returns:
            SelfCheckOutcome（ok=False 时调用方应判任务失败，不落库）

        规则：
            R1 分值白名单（含历史档容忍）
            R2 有分必有据
            R3 建议等级与区间一致性（以区间为准）
            R4 evidence_score<=25 → 等级上限 S3
            R5 固定 S4（evidence_score==0）→ 等级 S4
            R6 潜在档（is_potential 或命中 signal_category）→ 上限 S3
            R7 时效闸门（D8/D9）：最早影响评分的事实时间 超 12 个月滚动窗口 → 置 expired（不落库）
            R9 日期/来源纪律（D7）：publish_date == 跑批日、或命中行情/聚合页抑制表 → 剔除该条证据（不整体判失败）
    """
    notes: List[str] = []

    # R1 分值白名单（新档合法；历史档放过但记录）
    ev = score.evidence_score
    if ev is not None and ev not in VALID_EVIDENCE_SCORES:
        if ev in LEGACY_EVIDENCE_SCORES:
            notes.append(f"R1 evidence_score={ev} 属历史档（v2），已放过")
        else:
            return SelfCheckOutcome(
                ok=False,
                level_final=None,
                notes=[f"R1 非法 evidence_score={ev}"],
            )
    if score.specificity_score is not None and score.specificity_score not in VALID_SPECIFICITY_SCORES:
        return SelfCheckOutcome(
            ok=False,
            level_final=None,
            notes=[f"R1 非法 specificity_score={score.specificity_score}"],
        )

    run_date = today or validity.today_from()

    # R9 日期纪律与来源纪律（D7）：剔除「跑批日戳」与「行情/聚合页」证据
    dropped: List[int] = []
    drop_reasons: List[str] = []
    for idx, evidence in enumerate(score.evidences):
        if not evidence.kept:
            continue
        if str(evidence.source_type or "web").lower() == "knowledge_base":
            continue  # 知识库证据以 doc_id 为凭，不走发布日期/来源抑制
        if validity.is_run_date_stamp(evidence.publish_date, run_date):
            evidence.kept = False
            dropped.append(idx)
            drop_reasons.append(f"evidence_no={idx} 跑批日戳（publish_date == {run_date}）")
            continue
        suppressed, reason = sources.is_suppressed_url(evidence.url)
        if suppressed:
            evidence.kept = False
            dropped.append(idx)
            drop_reasons.append(f"evidence_no={idx} {reason}")
    if dropped:
        notes.append("R9 剔除证据：" + "；".join(drop_reasons))

    # R7 时效闸门（D8/D9）：基准＝该簇**最早影响评分的事实时间**；超窗 → 视同失效（decide_action 会 NOOP 不落库）
    if score.exhibition_related and not score.expired_or_done and (score.total_score or 0) > 0:
        basis = score.fact_time_earliest or score.signal_time
        basis_src = "fact_time_earliest" if score.fact_time_earliest else "signal_time(回落)"
        # 基准矛盾检测（只检测、不改判）：候选无法判断"是否同簇"，自动改判会误杀 → 挂起待核验
        conflict = validity.basis_conflict(basis, [e.model_dump() for e in score.evidences])
        if conflict is not None:
            if (score.admission_hint or "").strip().lower() == "pass":
                score.admission_hint = "pending_verify"
            notes.append(f"R7 基准存疑（挂起待核验）：{conflict['why']}")
        within, why = validity.is_within_validity(basis, run_date)
        notes.append(f"R7 时效基准 {basis_src}={basis!r} → {why}")
        if not within:
            score.expired_or_done = True
            score.admission_hint = "expired"
            score.total_score = None
            score.evidence_score = None
            score.specificity_score = None
            score.suggested_level = None
            notes.append(
                f"R7 判 expired：超窗不落库（窗口下界 {validity.validity_floor(run_date)}，"
                f"窗宽 {validity.validity_months()} 个月）"
            )
            return SelfCheckOutcome(
                ok=True,
                level_final=None,
                notes=notes,
                dropped_evidence_nos=dropped,
            )

    # 不准入 / 失效：无等级
    excluded = (not score.exhibition_related) or score.expired_or_done
    if excluded or score.total_score is None:
        return SelfCheckOutcome(
            ok=True, level_final=None, notes=notes, dropped_evidence_nos=dropped
        )

    has_score = score.total_score > 0

    # R2 有分必有据
    if has_score and not _has_valid_evidence(score):
        return SelfCheckOutcome(
            ok=False,
            level_final=None,
            notes=notes + ["R2 有分必有据：未找到有效 kept 证据（http url/doc_id）"],
            dropped_evidence_nos=dropped,
        )

    # R3 建议等级 vs 区间一致性（以区间为准）
    level = level_from_total(score.total_score)
    suggested = (score.suggested_level or "").strip().upper() or None
    if suggested and suggested in _LEVEL_RANK and suggested != level:
        notes.append(f"R3 建议等级 {suggested} 与区间推导 {level} 不一致，以 {level} 为准")

    # R4 潜在/弱档封顶：evidence_score<=25 → 最高 S3
    cap_reason: Optional[str] = None
    if ev is not None and ev <= 25:
        capped = _cap_at_most(level, "S3")
        if capped != level:
            cap_reason = "evidence_score<=25，最高 S3"
            level = capped

    # R6 潜在档封顶：is_potential 或命中 signal_category → 最高 S3
    if score.is_potential or (score.signal_category and str(score.signal_category).strip()):
        capped = _cap_at_most(level, "S3")
        if capped != level:
            cap_reason = (cap_reason + "; " if cap_reason else "") + "潜在信号，最高 S3"
            level = capped

    # R5 固定 S4：evidence_score==0 → S4（0+15=15 天然落 S4，此处显式复核）
    if ev == 0:
        if level != "S4":
            cap_reason = (cap_reason + "; " if cap_reason else "") + "固定 S4（0 分档）"
            level = "S4"

    return SelfCheckOutcome(
        ok=True,
        level_final=level,
        cap_reason=cap_reason,
        notes=notes,
        dropped_evidence_nos=dropped,
    )