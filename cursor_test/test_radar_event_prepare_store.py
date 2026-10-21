"""
M2 prepare + M7 radar_event_store 单元测试（纯函数，不连库）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.app.api.schemas.huayuan_radar_event import (
    RadarEventEvidenceItem,
    RadarEventScoreResult,
)
from radar_score.radar_event_store import (
    _bit,
    _event_columns,
    _normalize_priority,
    _resolve_level_verify_admission,
)
from radar_score.self_check import check
from radar_score.prepare import (
    _bit_bool,
    _company_context,
    _group_latest_by_root,
    _is_closed_row,
    build_history_json,
    build_request_body,
)
from radar_score import region_resolve


def _job() -> dict:
    return {"id": 9001, "company_id": 123, "time_from": None, "time_to": None, "tenant_id": 0}


def _company() -> dict:
    return {
        "id": 123,
        "name": "示例科技股份有限公司",
        "stock_code": "000001",
        "stock_name_raw": "示例科技",
        "industry": "软件",
        "region": "上海",
    }


def _score(**kw) -> RadarEventScoreResult:
    base = dict(
        exhibition_related=True,
        subject_confidence="high",
        space_object="展示中心",
        action="建设",
        signal_summary="公告披露拟建设展示中心",
        signal_time="2026-09-01",
        evidence_score=75,
        specificity_score=10,
        total_score=85,
        admission_hint="pending_verify",
        fact_status="confirmed",
        suggested_level="S1",
        procurement_scope="intent_phase",
        event_stage="planned",
        exhibition_stage="planned",
        verify_priority_adjusted="P1",
        rule_version="v3-2026-10-14",
        evidences=[
            RadarEventEvidenceItem(
                evidence_no=0, source_type="web", url="https://ex.com/a", kept=True
            )
        ],
    )
    base.update(kw)
    return RadarEventScoreResult(**base)


# ---------------- 纯函数 ----------------


def test_bit_and_priority() -> None:
    assert _bit(True) == 1 and _bit(False) == 0
    assert _normalize_priority("p0") == "P0"
    assert _normalize_priority("P5") is None
    assert _normalize_priority(None) is None


def test_bit_bool_mysql_bit() -> None:
    """MySQL bit 列 b'\\x00' 必须为 False（pymysql 返回 bytes 的坑）。"""
    assert _bit_bool(b"\x00") is False
    assert _bit_bool(b"\x01") is True
    assert _bit_bool(0) is False
    assert _bit_bool(1) is True
    assert _bit_bool(False) is False
    assert _bit_bool(True) is True


def test_company_context_aliases() -> None:
    ctx = _company_context(_company())
    assert ctx["company_name"] == "示例科技股份有限公司"
    assert ctx["stock_code"] == "000001"
    assert "示例科技" in ctx["aliases"]  # 简称进别名


def test_build_request_body_shape() -> None:
    history = [{"id": 1, "space_object": "老展厅", "system_level": "S4", "expired_or_done": True}]
    body = build_request_body(_job(), _company(), history, trace_id="t123")
    assert body["trace_id"] == "t123"
    ctx = body["context"]
    assert ctx["event_job_id"] == 9001
    assert ctx["company"]["company_name"] == "示例科技股份有限公司"
    assert json.loads(ctx["history_events_json"])[0]["id"] == 1
    assert build_history_json([]) == "[]"


def test_resolve_admission_normal_active() -> None:
    s = _score()
    derived = _resolve_level_verify_admission(s, check(s))
    assert derived["admission_pass"] == 1
    assert derived["system_level"] == "S1"
    assert derived["validity_status"] == "ACTIVE"
    assert derived["verify_status"] == "PENDING_VERIFY"  # 高分 + pending_verify


def test_resolve_admission_expired() -> None:
    s = _score(expired_or_done=True)
    derived = _resolve_level_verify_admission(s, check(s))
    assert derived["admission_pass"] == 0
    assert derived["system_level"] is None
    assert derived["validity_status"] == "EXPIRED"


def test_resolve_admission_reject_unrelated() -> None:
    s = _score(exhibition_related=False, admission_hint="reject_unrelated")
    derived = _resolve_level_verify_admission(s, check(s))
    assert derived["admission_pass"] == 0
    assert derived["validity_status"] == "INVALID"


def test_event_columns_mapping() -> None:
    s = _score()
    cols = _event_columns(_job(), s, check(s), "trace-1")
    assert cols["company_id"] == 123
    assert cols["event_job_id"] == 9001
    assert cols["system_level"] == "S1"
    assert cols["suggested_level"] == "S1"
    assert cols["procurement_scope"] == "intent_phase"
    assert cols["event_stage"] == "planned"
    assert cols["verify_priority_adjusted"] == "P1"
    assert cols["rule_version"] == "v3-2026-10-14"
    assert cols["agent_trace_id"] == "trace-1"
    assert cols["is_potential"] == 0
    # score_items 序列化为 JSON
    assert json.loads(cols["score_items_json"]) is not None or cols["score_items_json"] is None


# ---------------- 展厅所在区域（region_resolve）----------------

_BEIJING_CITY = {
    "id": 110100,
    "parent_id": 110000,
    "level": 3,
    "name": "北京市",
    "name_en": None,
    "full_name": "北京市 北京市",
    "path_ids": "1/110000/110100",
    "country_id": 1,
    "country_code": "CN",
    "is_domestic": b"\x01",
}
_BEIJING_PROVINCE = {**_BEIJING_CITY, "id": 110000, "level": 2, "full_name": "北京市", "path_ids": "1/110000"}


class _FakeCursor:
    """按 SQL 关键字路由返回行的假游标。"""

    def __init__(self, route):
        self._route = route
        self._rows: list[dict] = []

    def execute(self, sql, params):
        self._rows = self._route(sql, params)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    """最小连接桩：cursor() 返回 _FakeCursor。"""

    def __init__(self, route):
        self._route = route

    def cursor(self):
        return _FakeCursor(self._route)


def test_bit_int_mysql_bit() -> None:
    assert region_resolve._bit_int(b"\x01") == 1
    assert region_resolve._bit_int(b"\x00") == 0
    assert region_resolve._bit_int(None) is None
    assert region_resolve._bit_int(True) == 1


def test_pick_best_prefers_finer_level() -> None:
    assert region_resolve._pick_best([_BEIJING_PROVINCE, _BEIJING_CITY])["id"] == 110100
    assert region_resolve._pick_best([]) is None


def test_resolve_region_by_text_exact_name() -> None:
    """名称精确命中且同名时取城市级（level 更大）。"""
    def route(sql, params):
        if "FROM region WHERE name =" in sql:
            return [_BEIJING_PROVINCE, _BEIJING_CITY]
        return []

    region = region_resolve.resolve_region_by_text(_FakeConn(route), "北京市")
    assert region["id"] == 110100
    assert region["path_ids"] == "1/110000/110100"


def test_resolve_region_by_text_code_and_alias() -> None:
    """编码精确优先；编码未命中时走别名精确。"""
    def route(sql, params):
        if "FROM region WHERE code =" in sql:
            return []
        if "FROM region_alias WHERE alias =" in sql:
            return [{"region_id": 110100}]
        if "FROM region WHERE id =" in sql:
            return [_BEIJING_CITY]
        return []

    region = region_resolve.resolve_region_by_text(_FakeConn(route), "北京")
    assert region["id"] == 110100


def test_resolve_region_by_text_not_found() -> None:
    """全部步骤未命中返回 None（不补造）。"""
    assert region_resolve.resolve_region_by_text(_FakeConn(lambda s, p: []), "某不存在的地名") is None


def test_resolve_event_region_ai_parsed(monkeypatch) -> None:
    """place 命中 → AI_PARSED，并带出区域列与 is_domestic=1。"""
    monkeypatch.setattr(region_resolve, "resolve_region_by_text", lambda conn, text: _BEIJING_CITY)
    cols = region_resolve.resolve_event_region(None, "北京市", {"region_id": 999})
    assert cols["region_source"] == region_resolve.SOURCE_AI_PARSED
    assert cols["region_id"] == 110100
    assert cols["region_name"] == "北京市 北京市"
    assert cols["region_path_ids"] == "1/110000/110100"
    assert cols["country_id"] == 1
    assert cols["is_domestic"] == 1


def test_resolve_event_region_company_inherited(monkeypatch) -> None:
    """place 未命中 → 继承企业区域，来源 COMPANY_INHERITED。"""
    monkeypatch.setattr(region_resolve, "resolve_region_by_text", lambda conn, text: None)
    monkeypatch.setattr(region_resolve, "resolve_company_region", lambda conn, company: _BEIJING_CITY)
    cols = region_resolve.resolve_event_region(None, "unknown", {"region_id": 110100})
    assert cols["region_source"] == region_resolve.SOURCE_COMPANY_INHERITED
    assert cols["region_id"] == 110100


def test_resolve_event_region_unknown(monkeypatch) -> None:
    """都解析不到 → 区域留空、来源 UNKNOWN。"""
    monkeypatch.setattr(region_resolve, "resolve_region_by_text", lambda conn, text: None)
    monkeypatch.setattr(region_resolve, "resolve_company_region", lambda conn, company: None)
    cols = region_resolve.resolve_event_region(None, None, {})
    assert cols["region_source"] == region_resolve.SOURCE_UNKNOWN
    assert cols["region_id"] is None and cols["is_domestic"] is None


def test_event_columns_with_region() -> None:
    """传入 region 时并入区域列；不传时不含区域列（保留既有值）。"""
    s = _score()
    region = region_resolve._to_columns(_BEIJING_CITY, region_resolve.SOURCE_AI_PARSED)
    cols = _event_columns(_job(), s, check(s), "trace-1", region)
    assert cols["region_id"] == 110100
    assert cols["is_domestic"] == 1
    assert cols["region_source"] == "AI_PARSED"

    cols_no_region = _event_columns(_job(), s, check(s), "trace-1")
    assert "region_id" not in cols_no_region


# ---------------- 列宽截断 / 失败处置 ----------------

from radar_score.radar_event_store import _clip, _clip_optional_text, _EVENT_MAX  # noqa: E402
from radar_score.repository import (  # noqa: E402
    STATUS_FAILED,
    STATUS_PENDING,
    next_status,
)


def test_clip_respects_column_width() -> None:
    assert _clip(None, 10) is None
    assert _clip(123, 10) == 123
    assert _clip("abcd", 10) == "abcd"
    assert _clip("x" * 40, 10) == "x" * 10
    assert len(_clip("中" * 1000, _EVENT_MAX["time_text"])) == _EVENT_MAX["time_text"]


def test_clip_optional_text_blank_to_none() -> None:
    assert _clip_optional_text("", 200) is None
    assert _clip_optional_text("   ", 200) is None
    assert _clip_optional_text(" 信号 ", 200) == "信号"
    assert _clip_optional_text("y" * 500, 200) == "y" * 200


def test_event_columns_clip_overlong_strings() -> None:
    """超长字段必须被截断，避免 MySQL 1406 整单回滚。"""
    s = _score(
        time_text="t" * 300,
        score_reason="r" * 8000,
        suggested_level_reason="s" * 3000,
        verify_priority_reason="v" * 3000,
        signal_summary="   ",
    )
    cols = _event_columns(_job(), s, check(s), "trace-1")
    assert len(cols["time_text"]) == _EVENT_MAX["time_text"]
    assert len(cols["score_reason"]) == _EVENT_MAX["score_reason"]
    assert len(cols["suggested_level_reason"]) == _EVENT_MAX["suggested_level_reason"]
    assert len(cols["verify_priority_reason"]) == _EVENT_MAX["verify_priority_reason"]
    assert cols["signal_summary"] is None  # 空串归一为 NULL


def test_region_source_fits_column() -> None:
    """COMPANY_INHERITED(17) 必须放得进 region_source（曾因 varchar(16) 报 1406）。"""
    cols = region_resolve._to_columns(_BEIJING_CITY, region_resolve.SOURCE_COMPANY_INHERITED)
    assert cols["region_source"] == "COMPANY_INHERITED"
    assert len(cols["region_source"]) <= _EVENT_MAX["region_source"]


def test_next_status_boundaries() -> None:
    """可重试未达上限 → PENDING；确定性错误或超上限 → FAILED。"""
    assert next_status(True, 0, 3) == STATUS_PENDING
    assert next_status(True, 2, 3) == STATUS_PENDING  # 第 3 次重试仍允许
    assert next_status(True, 3, 3) == STATUS_FAILED  # 超过上限
    assert next_status(False, 0, 3) == STATUS_FAILED  # 确定性错误立即失败


def test_is_retryable_classification() -> None:
    """数据/结构类确定性错误不重试；网络/依赖抖动可重试。"""
    import pymysql

    from radar_score.execute import is_retryable

    assert is_retryable(pymysql.err.DataError(1406, "Data too long")) is False
    assert is_retryable(pymysql.err.ProgrammingError(1064, "syntax")) is False
    assert is_retryable(ValueError("bad schema")) is False
    assert is_retryable(pymysql.err.OperationalError(2013, "lost connection")) is True
    assert is_retryable(RuntimeError("gateway 502")) is True


def test_touch_latest_event_only_moves_forward() -> None:
    """企业最新事件指针只前移：SQL 带 latest_event_id < 条件。"""
    from radar_score.radar_event_store import touch_latest_event

    calls: list[tuple] = []

    class _Cur:
        rowcount = 1

        def execute(self, sql, params):
            calls.append((sql, params))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _Conn:
        def cursor(self):
            return _Cur()

    assert touch_latest_event(_Conn(), 3182, 5639) == 1
    sql, params = calls[0]
    assert "latest_event_id <" in sql
    assert params == [5639, 3182, 5639]


def test_touch_latest_event_skips_blank() -> None:
    """企业/事件为空时不查库。"""
    from radar_score.radar_event_store import touch_latest_event

    class _Conn:
        def cursor(self):
            raise AssertionError("不应查库")

    assert touch_latest_event(_Conn(), None, 1) == 0
    assert touch_latest_event(_Conn(), 1, None) == 0

# ---------------- history 族去重（261020） ----------------

def _hist_row(
    eid: int,
    *,
    parent=None,
    published=False,
    validity="ACTIVE",
    expired=False,
    update_time="2026-10-19 10:00:00",
    name=None,
):
    return {
        "id": eid,
        "parent_event_id": parent,
        "event_name": name,
        "published": published,
        "validity_status": validity,
        "expired_or_done": expired,
        "update_time": update_time,
    }


def test_group_latest_by_root_dedup_and_aggregate() -> None:
    """同族只留一条（最新作代表）；published 按族取"或"。"""
    rows = [
        _hist_row(5637, name="a", update_time="2026-10-19 15:52:05"),
        _hist_row(5639, parent=5637, update_time="2026-10-19 16:37:38"),
        _hist_row(5640, parent=5637, published=True, update_time="2026-10-19 18:03:38"),
        _hist_row(1462, name="b", update_time="2026-09-01 00:00:00"),
    ]
    groups = _group_latest_by_root(rows)
    assert len(groups) == 2
    g = next(x for x in groups if x["root_event_id"] == 5637)
    assert g["id"] == 5640  # 最新一条作代表
    assert g["published"] is True  # 已发布那条不是最新，也要按族取到
    assert g["member_count"] == 3
    assert sorted(g["member_ids"]) == [5637, 5639, 5640]
    # 代表行前的 root 组（1462）自成一组
    assert [x["root_event_id"] for x in groups] == [5637, 1462]


def test_group_closed_is_or() -> None:
    """族内任一条失效 → closed=True。"""
    rows = [
        _hist_row(1, update_time="2026-10-19 10:00:00"),
        _hist_row(2, parent=1, validity="INVALID", update_time="2026-10-19 11:00:00"),
    ]
    g = _group_latest_by_root(rows)[0]
    assert g["id"] == 2
    assert g["closed"] is True


def test_is_closed_row_variants() -> None:
    assert _is_closed_row({"validity_status": "INVALID"}) is True
    assert _is_closed_row({"expired_or_done": True}) is True
    assert _is_closed_row({"validity_status": "ACTIVE", "expired_or_done": False}) is False


# ---------------- 分段切分兜底（B，261020） ----------------

_CHAOYANG_BJ = {
    "id": 110105, "parent_id": 110100, "level": 4, "name": "朝阳区", "name_en": None,
    "full_name": "北京市 北京市 朝阳区", "path_ids": "1/110000/110100/110105",
    "country_id": 1, "country_code": "CN", "is_domestic": b"\x01",
}
_CHANGCHUN_CITY = {
    "id": 220100, "parent_id": 220000, "level": 3, "name": "长春市", "name_en": None,
    "full_name": "吉林省 长春市", "path_ids": "1/220000/220100",
    "country_id": 1, "country_code": "CN", "is_domestic": b"\x01",
}
_CHAOYANG_CC = {
    "id": 220104, "parent_id": 220100, "level": 4, "name": "朝阳区", "name_en": None,
    "full_name": "吉林省 长春市 朝阳区", "path_ids": "1/220000/220100/220104",
    "country_id": 1, "country_code": "CN", "is_domestic": b"\x01",
}


def test_clean_place_strips_noise() -> None:
    assert region_resolve._clean_place("重庆经开区东港片区（广滨三路）") == "重庆经开区东港片区"
    assert region_resolve._clean_place(" 北京市朝阳区 ") == "北京市朝阳区"
    assert region_resolve._clean_place(None) == ""


def test_split_place_candidates_fine_to_coarse() -> None:
    assert region_resolve._split_place_candidates("北京市朝阳区") == ["朝阳区", "北京市"]
    assert region_resolve._split_place_candidates("重庆经开区东港片区（广滨三路）") == ["东港片区", "重庆经开区"]
    assert region_resolve._split_place_candidates("美国旧金山") == ["美国旧金山"]
    assert region_resolve._split_place_candidates("") == []


def test_resolve_event_region_splitting_disambiguates(monkeypatch) -> None:
    """整串失败 → 分段切分命中朝阳区，并按父级"北京市"消歧到 110105。"""
    monkeypatch.setattr(region_resolve, "resolve_region_by_text", lambda conn, text: None)

    def route(sql, params):
        if "WHERE name =" in sql and params == ["朝阳区"]:
            return [_CHAOYANG_BJ, _CHAOYANG_CC]
        if "FROM region WHERE id =" in sql:
            return [_BEIJING_CITY] if params[0] == 110100 else [_CHANGCHUN_CITY]
        return []

    cols = region_resolve.resolve_event_region(_FakeConn(route), "北京市朝阳区", {"region_id": 999})
    assert cols["region_source"] == region_resolve.SOURCE_AI_PARSED
    assert cols["region_id"] == 110105


def test_resolve_event_region_splitting_picks_changchun(monkeypatch) -> None:
    """同名字段带"长春市" → 消歧到 220104。"""
    monkeypatch.setattr(region_resolve, "resolve_region_by_text", lambda conn, text: None)

    def route(sql, params):
        if "WHERE name =" in sql and params == ["朝阳区"]:
            return [_CHAOYANG_BJ, _CHAOYANG_CC]
        if "FROM region WHERE id =" in sql:
            return [_BEIJING_CITY] if params[0] == 110100 else [_CHANGCHUN_CITY]
        return []

    cols = region_resolve.resolve_event_region(_FakeConn(route), "吉林省长春市朝阳区", {"region_id": 999})
    assert cols["region_id"] == 220104
    assert cols["region_source"] == region_resolve.SOURCE_AI_PARSED


def test_has_district_token() -> None:
    assert region_resolve._has_district_token("北京市朝阳区") is True
    assert region_resolve._has_district_token("上海") is False
    assert region_resolve._has_district_token(None) is False


# ---------------- 证据落库映射（evidence_no / cite_reason，261020） ----------------

class _ExecConn:
    """最小连接桩：cursor() 返回自身，记录 executemany 的行。"""

    def __init__(self):
        self.insert_sql = ""
        self.rows = []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        return None

    def executemany(self, sql, rows):
        self.insert_sql = sql
        self.rows = rows


def test_replace_evidences_writes_evidence_no_and_cite_reason() -> None:
    """kept 证据按顺序写 evidence_no(0..n-1)；cite_reason 一并落库；kept=false 跳过。"""
    from radar_score.radar_event_store import replace_evidences

    score = RadarEventScoreResult(
        exhibition_related=True,
        signal_summary="x",
        evidences=[
            RadarEventEvidenceItem(evidence_no=0, title="a", url="https://a", quote="qa", cite_reason="r0", kept=True),
            RadarEventEvidenceItem(evidence_no=1, title="b", url="https://b", kept=False),
            RadarEventEvidenceItem(evidence_no=2, title="c", url="https://c", cite_reason="r2", kept=True),
        ],
    )
    conn = _ExecConn()
    n = replace_evidences(conn, 99, score, tenant_id=0)
    assert n == 2  # kept=false 的第 2 条不落
    assert "evidence_no" in conn.insert_sql and "cite_reason" in conn.insert_sql
    # 列序：event_id, evidence_no, title, summary, quote, cite_reason, ...
    assert conn.rows[0][0] == 99 and conn.rows[0][1] == 0 and conn.rows[0][2] == "a" and conn.rows[0][5] == "r0"
    assert conn.rows[1][1] == 1 and conn.rows[1][2] == "c" and conn.rows[1][5] == "r2"


def test_widened_text_columns_match_ddl() -> None:
    """加宽后的列宽必须与 DDL（48_/49_radar_widen_text_columns*.sql）一致，避免提前截断。"""
    from radar_score.radar_event_store import _EVIDENCE_MAX

    assert _EVENT_MAX["time_text"] == 128           # radar_event.time_text
    assert _EVENT_MAX["score_reason"] == 4000       # radar_event.score_reason
    assert _EVENT_MAX["signal_summary"] == 512      # radar_event.signal_summary
    assert _EVENT_MAX["region_path_ids"] == 512     # radar_event.region_path_ids
    assert _EVIDENCE_MAX["quote"] == 4000           # radar_event_evidence.quote
    assert _EVIDENCE_MAX["summary"] == 4000         # radar_event_evidence.summary
    assert _EVIDENCE_MAX["title"] == 1024           # radar_event_evidence.title
    assert _EVIDENCE_MAX["cite_reason"] == 2000     # radar_event_evidence.cite_reason
    assert _EVIDENCE_MAX["source_url"] == 2048      # radar_event_evidence.source_url


def test_is_retryable_walks_cause_chain() -> None:
    """路由把确定性 ValueError 包成 HTTPException 后，仍应判为不可重试（避免反复重跑）。"""
    import pymysql
    from fastapi import HTTPException

    from radar_score.execute import is_retryable

    try:
        try:
            raise ValueError("有分必有据：total_score>0 时…")
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
    except HTTPException as ex:
        assert is_retryable(ex) is False        # 沿 __cause__ 看到 ValueError → 不可重试
    assert is_retryable(pymysql.err.OperationalError(2003, "can't connect")) is True  # 抖动 → 可重试
