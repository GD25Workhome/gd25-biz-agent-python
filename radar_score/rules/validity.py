"""时效与日期纪律的共享纯函数（R7–R9）。

一条规则、多处调用：图内 `rule_gate` 用它**修订**，图外 `self_check` 用它**守门**；
两边同源调用，避免口径漂移。

口径（裁定 D7 / D8 / D9）：
- **有效事实窗口**＝评估日往回 ``SIGNAL_VALIDITY_MONTHS``（默认 12）个月的**滚动窗口**，
  每次评估现算（D9 = W1）；
- **基准时间**＝该簇**最早影响评分的事实时间**（立项 / 招标 / 签约），
  **不是**最新材料的发布日期（D8）；
- ``publish_date == 跑批日`` 视为**跑批日戳**，该条证据不可采信（D7）。

设计：``华院Agent设计/03-决策记录/261020-06-时效审查节点与证据日期纪律.md`` §3.1 / §3.8
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Optional, Tuple

# 有效事实窗口（月）；可用环境变量 SIGNAL_VALIDITY_MONTHS 覆盖
DEFAULT_SIGNAL_VALIDITY_MONTHS = 12
_ENV_MONTHS = "SIGNAL_VALIDITY_MONTHS"


def validity_months() -> int:
    """
        有效事实窗口月数（配置 ``SIGNAL_VALIDITY_MONTHS``，默认 12）。

        Returns:
            正整数月数；配置非法时回落默认值
    """
    raw = (os.getenv(_ENV_MONTHS) or "").strip()
    if not raw:
        return DEFAULT_SIGNAL_VALIDITY_MONTHS
    try:
        months = int(raw)
    except ValueError:
        return DEFAULT_SIGNAL_VALIDITY_MONTHS
    return months if months > 0 else DEFAULT_SIGNAL_VALIDITY_MONTHS


def _days_in_month(year: int, month: int) -> int:
    """该年该月的天数。"""
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days


def _shift_months(day: date, months: int) -> date:
    """把日期往前推 months 个月（月末按目标月天数收敛）。"""
    year, month = day.year, day.month - months
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, min(day.day, _days_in_month(year, month)))


def validity_floor(today: date, months: Optional[int] = None) -> date:
    """
        有效事实下界 ＝ 评估日往回 ``months`` 个月（滚动窗口，每次现算）。

        Args:
            today: 评估日
            months: 窗口月数；None 时读配置

        Returns:
            下界日期（早于它的事实时间视为超窗）
    """
    return _shift_months(today, validity_months() if months is None else months)


def parse_fact_date(text) -> Tuple[Optional[date], str]:
    """
        宽松解析"事实时间"文本 → (日期, 精度)。

        支持 ``YYYY-MM-DD`` / ``YYYY-MM`` / ``YYYY``；精度不足时取该区间**起点**
        （即最早可能时间，宁可偏保守）。解析失败返回 ``(None, "unknown")``。

        Args:
            text: 时间文本（可能为空）

        Returns:
            (日期或 None, "day"|"month"|"year"|"unknown")
    """
    raw = str(text or "").strip().replace("/", "-")
    if not raw:
        return None, "unknown"
    parts = raw.split("-")
    try:
        if len(parts) >= 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2])), "day"
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1), "month"
        if len(parts) == 1 and len(parts[0]) == 4:
            return date(int(parts[0]), 1, 1), "year"
    except (TypeError, ValueError):
        return None, "unknown"
    return None, "unknown"


def is_within_validity(
    fact_time, today: date, months: Optional[int] = None
) -> Tuple[bool, str]:
    """
        事实时间是否落在有效窗口内（R7 的判定核心）。

        Args:
            fact_time: 事实时间文本（最早影响评分的事实）
            today: 评估日
            months: 窗口月数；None 时读配置

        Returns:
            (是否有效, 说明)。**无法解析时间时返回 (True, "…交语义复核")** ——
            把"时间读不出来"交给 LLM 复核，而不是由代码判死。
    """
    day, precision = parse_fact_date(fact_time)
    if day is None:
        return True, "fact_time 无法解析，交语义复核"
    floor = validity_floor(today, months)
    if day < floor:
        return False, f"最早事实 {day}（{precision}）早于下界 {floor}，超窗"
    return True, f"最早事实 {day}（{precision}）不早于下界 {floor}"


def is_run_date_stamp(publish_date, run_date: date) -> bool:
    """
        证据发布日期是否等于跑批日（D7：跑批日戳）。

        Args:
            publish_date: 证据的 publish_date 文本
            run_date: 本次跑批日

        Returns:
            True 表示该日期就是跑批/抓取当天，不可采信
    """
    day, _ = parse_fact_date(publish_date)
    return day is not None and day == run_date


def today_from(dt: Optional[datetime] = None) -> date:
    """评估日（默认取当前本地日期）。"""
    return (dt or datetime.now()).date()


# ---------------------------------------------------------------------------
# 基准交叉校验（裁定 D8 的补口）：
# 模型可以"挑一条对自己有利的晚发布材料"当 `fact_time_earliest`（5333 实测：备案 2024，
# 却填 2025-11 上会稿，并自述"时效正常"）。所以基准**不能只信模型**，要用证据交叉校验。
# ---------------------------------------------------------------------------

# 证据里出现这些"展厅类实体词"才认作项目类证据（防 2010 年公司简介页之类的无关旧页）
_EVIDENCE_ENTITY_WORDS = (
    "展厅",
    "展馆",
    "展示",
    "体验中心",
    "陈列",
    "科技馆",
    "纪念馆",
    "培训中心",
    "接待中心",
    "展示中心",
)

# **必须同时**出现"项目动作词"才算项目类事实 —— 否则"来访参观了贵司展厅"这类旧闻会被误判为立项事实
_EVIDENCE_ACTION_WORDS = (
    "立项",
    "招标",
    "中标",
    "签约",
    "建设",
    "新建",
    "改造",
    "装修",
    "采购",
    "施工",
    "承建",
    "开工",
    "投资",
    "备案",
    "预算",
    "方案设计",
    "设计单位",
    "竣工",
    "扩建",
    "迁建",
    "布展",
    "展陈",
    "招采",
)

# 模型基准比证据候选晚超过这么多天才改判（容忍小差异，避免噪声）
EARLIEST_TOLERANCE_DAYS = 183


def earliest_project_fact(
    evidences,
) -> Tuple[Optional[date], Optional[int], str]:
    """
        从 kept 证据里推"项目类最早日期"候选，用于交叉校验模型给的基准。

        约束（防误判）：
        - 只认 kept、非 knowledge_base、日期可解析的证据；
        - 证据文本（`title` / `quote` / `cite_reason` / `summary`）必须**同时**含
          **展厅类实体词**与**项目动作词** —— 只提"参观/来访/听取汇报"的旧闻不算项目事实；
          也避免"公司 2010 年简介页"这类无关旧页把基准拉到很早。

        Args:
            evidences: 证据列表（raw dict，可含 `kept` / `publish_date` / `evidence_no`）

        Returns:
            (最早日期或 None, 对应 evidence_no 或 None, 说明)
    """
    best: Optional[date] = None
    best_no: Optional[int] = None
    best_why = ""
    for item in evidences or []:
        if not isinstance(item, dict) or not item.get("kept", True):
            continue
        if str(item.get("source_type") or "web").lower() == "knowledge_base":
            continue
        day, _ = parse_fact_date(item.get("publish_date"))
        if day is None:
            continue
        blob = " ".join(
            str(item.get(key) or "")
            for key in ("title", "quote", "cite_reason", "summary")
        )
        if not any(word in blob for word in _EVIDENCE_ENTITY_WORDS):
            continue
        if not any(word in blob for word in _EVIDENCE_ACTION_WORDS):
            continue  # 只有"参观/汇报"语境提及展厅 → 不是项目事实
        if best is None or day < best:
            best = day
            best_no = item.get("evidence_no")
            best_why = f"evidence_no={item.get('evidence_no')} publish_date={day}"
    return best, best_no, best_why


def basis_conflict(model_basis, evidences) -> Optional[Dict[str, Any]]:
    """
        检测"模型基准 vs 证据候选"是否矛盾（**只检测、不改判**）。

        为什么只检测：候选是"含展厅实体词 + 项目动作词的最早证据"，但它**无法判断是否同簇** ——
        实测（351 条存量）会把往年"建设/使用展厅"的旧事实（另一个已完成项目）误当本次最早事实，
        自动改判会误杀约 69%。同簇判断属**语义**，交 auditor(LLM) 与人工核验。

        Args:
            model_basis: 模型给的 `fact_time_earliest`（或回落的 `signal_time`）
            evidences: 证据列表（raw dict）

        Returns:
            矛盾信息 dict（`candidate` / `gap_days` / `why`）；无矛盾或证据不足返回 None
    """
    candidate, candidate_no, why = earliest_project_fact(evidences)
    if candidate is None:
        return None
    model_day, _ = parse_fact_date(model_basis)
    if model_day is None:
        return {
            "candidate": candidate.isoformat(),
            "candidate_evidence_no": candidate_no,
            "gap_days": None,
            "why": f"模型基准不可解析，证据候选 {candidate}（{why}）",
        }
    gap = (model_day - candidate).days
    if gap <= EARLIEST_TOLERANCE_DAYS:
        return None
    return {
        "candidate": candidate.isoformat(),
        "candidate_evidence_no": candidate_no,
        "gap_days": gap,
        "why": f"模型基准 {model_day} 比证据候选 {candidate} 晚 {gap} 天（{why}）",
    }


def reconcile_fact_time(model_basis, evidences) -> Tuple[str, str]:
    """
        兼容旧调用：返回 (基准, 说明)。**不再自动改判** —— 仅返回模型基准 + 矛盾说明。

        Args:
            model_basis: 模型给的时效基准
            evidences: 证据列表（raw dict）

        Returns:
            (采用的基准时间串, 说明)
    """
    conflict = basis_conflict(model_basis, evidences)
    if conflict is None:
        return (str(model_basis or ""), "基准无矛盾（或证据不足）")
    return (str(model_basis or ""), f"**基准存疑**（挂起待核验）：{conflict['why']}")