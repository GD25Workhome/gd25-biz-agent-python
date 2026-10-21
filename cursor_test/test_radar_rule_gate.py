"""radar_rule_gate 质检闸门节点（D10=形态 C 第 2 节点）单元测试。

覆盖：
- 流程定义：3 节点 + 条件边（不与 always 混用）；
- function 节点已注册；
- R7/R9 生效（超窗置 expired、跑批日戳/行情页剔除）；
- **双写 edges_var 与 persistence_edges_var**（坑 1）且**不污染上游**（坑 2）；
- 路由取到的是**修订值**（坑 1 的回归）。
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.app.api.routes.huayuan_radar_event import resolve_scores_from_flow_result
from backend.domain.flows.implementations.radar_rule_gate_node import RadarRuleGateNode
from backend.domain.flows.nodes.function_registry import function_registry
from backend.domain.flows.parser import FlowParser

_FLOW_DIR = _project_root / "config" / "flows" / "huayuan_radar_event_agent_v3"


def _state(
    *,
    scores: list[dict],
    evidences: list[dict],
    react_total: int | None = None,
) -> dict:
    """构造一个「第一节点刚跑完」的状态（react 写在 edges_var + persistence_edges_var）。"""
    bag = {"radar_event_scores": scores, "evidences": evidences, "discarded": []}
    if react_total is not None:
        bag["radar_event_score"] = dict(scores[0], total_score=react_total)
    return {
        "edges_var": {k: v for k, v in bag.items()},
        "persistence_edges_var": {k: v for k, v in bag.items()},
        "history_messages": [],
        "flow_msgs": [],
        "prompt_vars": {"current_date": "2026-10-20 12:00:00"},
    }


def _unexpired_event() -> dict:
    return {
        "event_ref": "e0",
        "exhibition_related": True,
        "signal_summary": "公告披露展厅建设",
        "signal_time": "2026-06-01",
        "fact_time_earliest": "2026-06-01",
        "fact_time_earliest_evidence_no": 0,
        "evidence_score": 75,
        "specificity_score": 10,
        "total_score": 85,
        "suggested_level": "S1",
        "expired_or_done": False,
        "admission_hint": "pass",
    }


def test_flow_definition_has_three_nodes_and_conditional_edge() -> None:
    """流程定义：3 节点；rule_gate 只有条件边；audit → END。"""
    flows = FlowParser.scan_flows_directory(_FLOW_DIR.parent)
    flow = flows["huayuan_radar_event_agent_v3"]
    names = [n.name for n in flow.nodes]
    assert names == ["radar_event_react_node", "radar_rule_gate", "radar_event_audit_node"]
    gate_edges = [e for e in flow.edges if e.from_node == "radar_rule_gate"]
    assert len(gate_edges) == 1 and gate_edges[0].condition != "always"
    assert gate_edges[0].to_node == "radar_event_audit_node"
    types = {n.name: n.type for n in flow.nodes}
    assert types["radar_rule_gate"] == "function"


def test_rule_gate_function_registered() -> None:
    """function 节点已注册（flow.yaml 的 function_key 能找到实现）。"""
    import backend.domain.flows.implementations  # noqa: F401  触发自动注册

    assert RadarRuleGateNode.get_key() == "radar_rule_gate_func"
    assert function_registry.get("radar_rule_gate_func") is RadarRuleGateNode


def test_rule_gate_double_writes_and_does_not_pollute_upstream() -> None:
    """双写两个 bag（坑 1）；上游 state 不被就地改写（坑 2）。"""
    ev = {"evidence_no": 0, "source_type": "web", "url": "https://ex.com/a",
          "kept": True, "publish_date": "2026-06-01"}
    state = _state(scores=[_unexpired_event()], evidences=[ev], react_total=85)
    out = asyncio.run(RadarRuleGateNode().execute(state))

    for bag_name in ("edges_var", "persistence_edges_var"):
        bag = out[bag_name]
        assert bag["radar_audit_required"] is True
        assert bag["radar_event_scores"][0]["total_score"] == 85
        assert bag["radar_event_score"]["total_score"] == 85  # 单对象形态同步
    # 上游未被污染：原 state 里没有 audit 标志
    assert "radar_audit_required" not in state["edges_var"]
    assert "radar_audit_required" not in state["persistence_edges_var"]
    # 下游备料：prompt_vars 里带上修订后 JSON（agent 节点只吃 history+current_message）
    assert "upstream_scores_json" in out["prompt_vars"]


def test_rule_gate_expires_out_of_window_and_drops_run_date_stamp() -> None:
    """R7 超窗置 expired（分置 null）；R9 剔除跑批日戳；有分事件仍要求复核。"""
    out_of_window = dict(_unexpired_event(), fact_time_earliest="2024-03-14", signal_time="2025-11-14")
    keep = _unexpired_event()
    keep["event_ref"] = "e1"
    evidences = [
        {"evidence_no": 0, "source_type": "web", "url": "https://ex.com/a", "kept": True,
         "publish_date": "2026-10-20"},                     # 跑批日戳 → 剔除
        {"evidence_no": 1, "source_type": "web",
         "url": "https://www.stcn.com/quotes/index/x.html", "kept": True,
         "publish_date": "2026-06-01"},                     # 行情页 → 剔除
        {"evidence_no": 2, "source_type": "web", "url": "https://ex.com/c", "kept": True,
         "publish_date": "2026-06-02"},                     # 正常
    ]
    state = _state(scores=[out_of_window, keep], evidences=evidences)
    node = RadarRuleGateNode()
    # 固定「跑批日」= 2026-10-20（与 publish_date 戳一致）
    import radar_score.rules.validity as v
    orig = v.today_from
    v.today_from = lambda *a, **k: date(2026, 10, 20)
    try:
        out = asyncio.run(node.execute(state))
    finally:
        v.today_from = orig

    bag = out["edges_var"]
    expired, kept = bag["radar_event_scores"]
    assert expired["expired_or_done"] is True and expired["admission_hint"] == "expired"
    assert expired["total_score"] is None and expired["evidence_score"] is None
    assert kept["expired_or_done"] is False and kept["total_score"] == 85
    assert bag["evidences"][0]["kept"] is False and "跑批日戳" in bag["evidences"][0]["drop_reason"]
    assert bag["evidences"][1]["kept"] is False and "行情" in bag["evidences"][1]["drop_reason"]
    assert bag["evidences"][2]["kept"] is True
    report = {r["event_ref"]: r for r in bag["radar_rule_gate_report"]["events"]}
    assert report["e0"]["expired"] is True
    assert report["e0"]["dropped_evidence_nos"] == [0, 1]
    assert bag["radar_audit_required"] is True   # e1 仍有分


def test_rule_gate_no_audit_when_nothing_has_score() -> None:
    """全部事件都无分/超窗 → 不进 auditor（D11：经硬闸后仍有分才审）。"""
    a = dict(_unexpired_event(), fact_time_earliest="2024-03-14")
    b = dict(_unexpired_event(), event_ref="e1", exhibition_related=False, total_score=None,
             evidence_score=None, specificity_score=None)
    state = _state(scores=[a, b], evidences=[
        {"evidence_no": 0, "source_type": "web", "url": "https://ex.com/a", "kept": True,
         "publish_date": "2026-06-01"}])
    out = asyncio.run(RadarRuleGateNode().execute(state))
    assert out["edges_var"]["radar_audit_required"] is False
    assert "upstream_scores_json" not in (out.get("prompt_vars") or {})


def test_route_resolves_revised_score_from_edges_var() -> None:
    """坑 1 回归：edges_var（修订值）优先于 persistence_edges_var（旧值）。"""
    result = {
        "edges_var": {
            "radar_event_scores": [_unexpired_event()],
            "evidences": [{"evidence_no": 0, "source_type": "web", "url": "https://ex.com/a",
                           "kept": True, "publish_date": "2026-06-01"}],
        },
        "persistence_edges_var": {"radar_event_scores": [dict(_unexpired_event(), total_score=35)]},
    }
    scores = resolve_scores_from_flow_result(result)
    assert len(scores) == 1 and scores[0].total_score == 85   # 修订值生效


def test_gate_and_self_check_agree_on_same_input() -> None:
    """2.11 验证：同源调用 —— 同一输入下 rule_gate 与 self_check 判定一致。"""
    from datetime import date as _date

    from backend.app.api.schemas.huayuan_radar_event import (
        RadarEventEvidenceItem,
        RadarEventScoreResult,
    )
    from backend.domain.flows.implementations.radar_rule_gate_node import apply_gate
    from radar_score.self_check import check

    run = _date(2026, 10, 20)
    # 图外：self_check
    score = RadarEventScoreResult(
        exhibition_related=True,
        signal_summary="公告披露展厅建设",
        signal_time="2025-11-14",
        fact_time_earliest="2024-03-14",
        evidence_score=75,
        specificity_score=10,
        total_score=85,
        evidences=[
            RadarEventEvidenceItem(evidence_no=0, source_type="web", url="https://ex.com/a",
                                   kept=True, publish_date="2026-10-20")  # 跑批日戳
        ],
    )
    out = check(score, today=run)
    # 图内：rule_gate
    events, evidences, report = apply_gate(
        [{
            "event_ref": "e0", "exhibition_related": True, "signal_summary": "x",
            "signal_time": "2025-11-14", "fact_time_earliest": "2024-03-14",
            "evidence_score": 75, "specificity_score": 10, "total_score": 85,
            "expired_or_done": False,
        }],
        [{"evidence_no": 0, "source_type": "web", "url": "https://ex.com/a", "kept": True,
          "publish_date": "2026-10-20"}],
        run,
    )
    # 两条路径：都判超窗 expired、都剔除跑批日戳证据
    assert score.expired_or_done is True and events[0]["expired_or_done"] is True
    assert score.total_score is None and events[0]["total_score"] is None
    assert out.dropped_evidence_nos == [0]
    assert report["events"][0]["dropped_evidence_nos"] == [0]
    assert evidences[0]["kept"] is False


def test_rule_gate_records_basis_conflict_and_holds() -> None:
    """图内：基准矛盾 → **不改判**，挂起 pending_verify 并把冲突写进留痕（供 auditor/人工定夺）。"""
    ev = dict(_unexpired_event(), fact_time_earliest="2025-11-14", signal_time="2026-01-23")
    evidences = [
        {"evidence_no": 0, "source_type": "web", "url": "https://ex.com/a", "kept": True,
         "publish_date": "2025-11-14", "quote": "招股书重申展厅建设"},
        {"evidence_no": 1, "source_type": "web", "url": "https://ex.com/b", "kept": True,
         "publish_date": "2024-03-14", "quote": "建设培训中心和展厅，已取得投资项目备案证"},
    ]
    import radar_score.rules.validity as v
    orig = v.today_from
    v.today_from = lambda *a, **k: date(2026, 10, 20)
    try:
        out = asyncio.run(RadarRuleGateNode().execute(_state(scores=[ev], evidences=evidences)))
    finally:
        v.today_from = orig
    bag = out["edges_var"]
    e0 = bag["radar_event_scores"][0]
    assert e0["expired_or_done"] is False                 # 不误杀
    assert e0["admission_hint"] == "pending_verify"       # 挂起待核验
    assert e0["fact_time_conflict"]["candidate"] == "2024-03-14"
    assert bag["radar_audit_required"] is True            # 仍有分 → 进 auditor 语义复核
    rep = bag["radar_rule_gate_report"]["events"][0]
    assert rep["basis_conflict"]["gap_days"] > 183


# ---------------- 复核留痕（裁定 D12）：before/after 与路由暴露 ----------------

def test_gate_report_has_before_and_after() -> None:
    """留痕报告必须含「修改前全量 + 修改后」，供落库 revision_json。"""
    ev = dict(_unexpired_event(), fact_time_earliest="2025-11-14", signal_time="2026-01-23")
    evidences = [
        {"evidence_no": 0, "source_type": "web", "url": "https://ex.com/b", "kept": True,
         "publish_date": "2024-03-14", "quote": "建设培训中心和展厅，已取得投资项目备案证"},
    ]
    import radar_score.rules.validity as v
    orig = v.today_from
    v.today_from = lambda *a, **k: date(2026, 10, 20)
    try:
        out = asyncio.run(RadarRuleGateNode().execute(_state(scores=[ev], evidences=evidences)))
    finally:
        v.today_from = orig
    rep = out["edges_var"]["radar_rule_gate_report"]
    assert rep["by"] == "rule_gate"
    assert rep["validity_floor"] == "2025-10-20"
    assert rep["expired_count"] == 0          # 基准矛盾 → 挂起（不再自动改判/误杀）
    assert rep["audit_required"] is True      # 仍有分 → 进 auditor
    assert rep["before"][0]["admission_hint"] == "pass"            # 修改前
    assert rep["after"][0]["admission_hint"] == "pending_verify"   # 修改后（挂起待核验）
    assert rep["after"][0]["fact_time_conflict"]["candidate"] == "2024-03-14"
    assert "fact_time_conflict" not in rep["before"][0]


def test_route_collects_revision_from_bags() -> None:
    """路由把 rule_gate 报告与 audit 说明收集进响应 revision（D12 落库入口）。"""
    from backend.app.api.routes.huayuan_radar_event import _collect_revision

    result = {
        "edges_var": {"radar_rule_gate_report": {"by": "rule_gate", "expired_count": 1}},
        "persistence_edges_var": {"audit": {"changed": True, "verdicts": [{"event_ref": "e0"}]}},
    }
    rev = _collect_revision(result)
    assert rev["rule_gate"]["expired_count"] == 1
    assert rev["audit"]["changed"] is True
    assert _collect_revision({"edges_var": {}}) is None
