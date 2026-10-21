"""规则二 v3 质检闸门节点（D10 = 形态 C 的第 2 个节点；type: function）。

定位：图内「**改好**」—— 只做**确定性**规则，把"能算的错"在流程内直接修掉；
与图外 `self_check`（「拦住」，fail-closed）**同源调用** `radar_score/rules/*`。

职责：
- **R9** 日期 / 来源纪律（D7）：剔除「跑批日戳」与「行情 / 聚合页」证据；
- **R7** 时效闸门（D8/D9）：最早影响评分的事实时间 超 12 个月滚动窗口 → 置 `expired`；
- 产出 **`radar_audit_required`**：经硬闸后**仍有分**的事件存在 → 交 `auditor` 做语义复核（D11）。

⚠️ 两条实现约束（见 `261020-06` §3.4，踩过就知道难查）：
1. **必须同时覆盖 `edges_var` 与 `persistence_edges_var`** —— 路由 `resolve_scores_from_flow_result`
   先读 `edges_var` 且**命中即返回**，只写 persistence 会被上一节点的旧值遮住（表现为"改了没生效"）；
2. `state` 是**浅拷贝**，改任何 dict 前先自行 `copy`，否则污染上游状态。

设计：`华院Agent设计/03-决策记录/261020-06-时效审查节点与证据日期纪律.md` §3.6 / §3.8
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

from langchain_core.messages import HumanMessage

from backend.domain.flows.nodes.base_function import BaseFunctionNode
from backend.domain.state import FlowState
from radar_score.rules import sources, validity

logger = logging.getLogger(__name__)

_KEY_SCORES = "radar_event_scores"
_KEY_SCORE_SINGLE = "radar_event_score"
_KEY_EVIDENCES = "evidences"
_KEY_DISCARDED = "discarded"
_KEY_AUDIT_FLAG = "radar_audit_required"
_KEY_REPORT = "radar_rule_gate_report"

_SCORE_FIELDS_TO_NULL = (
    "total_score",
    "evidence_score",
    "specificity_score",
    "suggested_level",
)


def _events_of(bag: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 bag 里取出事件列表（数组优先，兼容单对象）。"""
    arr = bag.get(_KEY_SCORES)
    if isinstance(arr, list) and arr:
        return [e for e in arr if isinstance(e, dict)]
    single = bag.get(_KEY_SCORE_SINGLE)
    if isinstance(single, dict):
        return [single]
    return []


def _copy_evidences(items: Any) -> List[Dict[str, Any]]:
    """证据列表浅拷贝（每条也拷贝，避免改上游）。"""
    if not isinstance(items, list):
        return []
    return [dict(e) for e in items if isinstance(e, dict)]


def _apply_r9(evidences: List[Dict[str, Any]], run_date) -> Tuple[List[Dict[str, Any]], List[int]]:
    """
        R9：剔除跑批日戳与行情/聚合页证据（就地改 copy 出来的条目）。

        Args:
            evidences: 已拷贝的证据 dict 列表
            run_date: 跑批日

        Returns:
            (证据列表, 被剔除的 evidence_no 列表)
    """
    dropped: List[int] = []
    for item in evidences:
        if not item.get("kept", True):
            continue
        if str(item.get("source_type") or "web").lower() == "knowledge_base":
            continue  # 知识库证据以 doc_id 为凭
        reason = ""
        if validity.is_run_date_stamp(item.get("publish_date"), run_date):
            reason = f"跑批日戳（publish_date == {run_date}）"
        else:
            suppressed, why = sources.is_suppressed_url(item.get("url"))
            if suppressed:
                reason = why
        if reason:
            item["kept"] = False
            item["drop_reason"] = reason
            no = item.get("evidence_no")
            if isinstance(no, int):
                dropped.append(no)
    return evidences, dropped


def _apply_r7(event: Dict[str, Any], run_date, evidences: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
        R7：时效闸门（就地改 copy 出来的事件）。

        Args:
            event: 事件 dict（会被就地修改）
            run_date: 跑批日
            evidences: 顶层共享证据（用于基准交叉校验）

        Returns:
            (是否判为 expired, 说明)
    """
    if event.get("expired_or_done"):
        return True, "模型已判失效"
    if not event.get("exhibition_related"):
        return False, "展厅无关，不走时效闸门"
    if (event.get("total_score") or 0) <= 0:
        return False, "无分，不走时效闸门"
    model_basis = event.get("fact_time_earliest") or event.get("signal_time")
    # 基准矛盾检测（只检测、不改判）：候选无法判断"是否同簇"，自动改判会误杀 → 挂起待核验
    conflict = validity.basis_conflict(model_basis, evidences)
    if conflict is not None:
        event["fact_time_conflict"] = conflict
        if str(event.get("admission_hint") or "").strip().lower() == "pass":
            event["admission_hint"] = "pending_verify"
    basis = model_basis
    within, why = validity.is_within_validity(basis, run_date)
    if within:
        return False, why
    event["expired_or_done"] = True
    event["admission_hint"] = "expired"
    for field in _SCORE_FIELDS_TO_NULL:
        event[field] = None
    return True, why


def apply_gate(
    events: List[Dict[str, Any]], evidences: List[Dict[str, Any]], run_date
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
        对（已拷贝的）事件与证据执行 R7 / R9，返回修订结果与**留痕报告**。

        报告含「修改前全量（`before`）+ 修改后（`after`）+ 逐事件判定 + 依据」，
        供落库到 `radar_event_job.revision_json`（裁定 D12）。

        Args:
            events: 事件 dict 列表（**会被就地修改**）
            evidences: 顶层共享证据（**会被就地修改**）
            run_date: 跑批日

        Returns:
            (events, evidences, report)
    """
    # 修改前全量快照（JSON 往返，避免嵌套对象被后续就地修改影响）
    before = json.loads(json.dumps(events, ensure_ascii=False, default=str))

    evidences, shared_drops = _apply_r9(evidences, run_date)
    entries: List[Dict[str, Any]] = []
    for idx, event in enumerate(events):
        item_drops: List[int] = []
        if isinstance(event.get(_KEY_EVIDENCES), list) and event[_KEY_EVIDENCES]:
            event[_KEY_EVIDENCES], item_drops = _apply_r9(_copy_evidences(event[_KEY_EVIDENCES]), run_date)
        expired, why = _apply_r7(event, run_date, evidences)
        entries.append(
            {
                "event_ref": event.get("event_ref") or f"e{idx}",
                "expired": expired,
                "expired_reason": why if expired else None,
                "fact_time_basis": event.get("fact_time_earliest"),
                "basis_conflict": event.get("fact_time_conflict"),
                "dropped_evidence_nos": sorted(set(shared_drops + item_drops)),
                "has_score_after_gate": (event.get("total_score") or 0) > 0,
            }
        )
    report: Dict[str, Any] = {
        "by": "rule_gate",
        "validity_floor": validity.validity_floor(run_date).isoformat(),
        "validity_months": validity.validity_months(),
        "expired_count": sum(1 for e in entries if e["expired"]),
        "dropped_evidence_nos": sorted({n for e in entries for n in e["dropped_evidence_nos"]}),
        "audit_required": any(e["has_score_after_gate"] for e in entries),
        "events": entries,
        "before": before,
        "after": events,
    }
    return events, evidences, report


class RadarRuleGateNode(BaseFunctionNode):
    """规则二 v3 质检闸门（确定性规则，图内修订）。"""

    @classmethod
    def get_key(cls) -> str:
        """Function 节点注册键（flow.yaml 的 function_key）。"""
        return "radar_rule_gate_func"

    async def execute(self, state: FlowState) -> FlowState:
        """执行质检：R7/R9 → 写回两个 bag + 决定是否语义复核。"""
        # 1. 浅拷贝兜底：任何 dict 都要自己 copy，避免污染上游（坑 2）
        new_state = dict(state)
        edges = dict(state.get("edges_var") or {})
        persisted = dict(state.get("persistence_edges_var") or {})

        # 2. 取事件与证据（edges_var 优先，回退 persistence）
        events = [dict(e) for e in _events_of(edges)] or [dict(e) for e in _events_of(persisted)]
        if not events:
            logger.warning("[rule_gate] 未找到 radar_event_scores，跳过质检")
            new_state["edges_var"] = edges
            new_state["persistence_edges_var"] = persisted
            return new_state

        source_bag = edges if _events_of(edges) else persisted
        evidences = _copy_evidences(source_bag.get(_KEY_EVIDENCES))
        discarded = source_bag.get(_KEY_DISCARDED)
        discarded = list(discarded) if isinstance(discarded, list) else []

        # 3. 跑规则（与图外 self_check 同源：radar_score/rules/*）
        run_date = validity.today_from()
        events, evidences, report = apply_gate(events, evidences, run_date)
        audit_required = bool(report.get("audit_required"))

        # 4. 双写两个 bag（坑 1：路由先读 edges_var 且命中即返回）
        for bag in (edges, persisted):
            bag[_KEY_SCORES] = events
            if _KEY_SCORE_SINGLE in bag:
                bag[_KEY_SCORE_SINGLE] = events[0]
            bag[_KEY_EVIDENCES] = evidences
            bag[_KEY_DISCARDED] = discarded
            bag[_KEY_AUDIT_FLAG] = audit_required
            bag[_KEY_REPORT] = report
        new_state["edges_var"] = edges
        new_state["persistence_edges_var"] = persisted

        expired_n = int(report.get("expired_count") or 0)
        dropped_n = len(report.get("dropped_evidence_nos") or [])
        logger.info(
            "[rule_gate] events=%s expired=%s droppedEvidence=%s auditRequired=%s floor=%s",
            len(events),
            expired_n,
            dropped_n,
            audit_required,
            validity.validity_floor(run_date),
        )

        # 5. 给下游 auditor 备料：写进 prompt_vars（下游系统提示用占位符读；agent 节点只吃 history+current_message，不吃 flow_msgs）
        if audit_required:
            prompt_vars = dict(state.get("prompt_vars") or {})
            prompt_vars["upstream_scores_json"] = json.dumps(
                {
                    "radar_event_scores": events,
                    "evidences": evidences,
                    "discarded": discarded,
                    "rule_gate_report": report,
                },
                ensure_ascii=False,
                default=str,
            )
            new_state["prompt_vars"] = prompt_vars
            new_state["current_message"] = HumanMessage(
                content=(
                    "请按系统提示中的**时效核查清单**复核 `{upstream_scores_json}`（见系统提示），"
                    "只允许向下修正；输出与输入同结构的单个 JSON 对象。"
                )
            )
        return new_state