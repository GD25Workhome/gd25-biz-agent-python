"""
华院规则二 /radar-event-score 单元测试

覆盖：Schema、上下文限流、权威档启发式、评分解析、非法分值、路由 mock。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from pydantic import ValidationError

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.app.api.routes.huayuan_radar_event import (
    HUAYUAN_RADAR_EVENT_FLOW_KEY,
    parse_radar_event_score_from_ai_text,
    router as radar_event_router,
)
from backend.app.api.schemas.huayuan_radar_event import HuayuanRadarEventRequest
from backend.domain.tools.huayuan_radar_event_context import (
    build_radar_event_context_from_request,
    classify_authority_tier,
    extract_source_host,
    text_mentions_subject,
)


def _sample_request_body() -> dict:
    """构造联调样例请求体（鼎捷数智）。"""
    return {
        "query": "请根据公开信息评估该公司展厅项目需求证据强度，并给出评分与证据。",
        "context": {
            "event_job_id": 1001,
            "company": {
                "company_id": 12,
                "company_name": "鼎捷数智",
                "stock_code": "300378",
                "aliases": ["鼎捷软件"],
            },
            "time_from": "2025-01-01",
            "time_to": "2026-09-09",
            "max_search_times": 3,
            "max_extract_times": 2,
        },
        "trace_id": "b" * 32,
    }


def _sample_score_json(**overrides: object) -> dict:
    """构造合法评分 JSON。"""
    data: dict = {
        "exhibition_related": True,
        "subject_confidence": "high",
        "space_object": "企业展厅",
        "action": "升级改造意向",
        "place": None,
        "time_text": "2026年",
        "evidence_score": 60,
        "specificity_score": 10,
        "total_score": 70,
        "tags": ["升级改造"],
        "expired_or_done": False,
        "fact_status": "inferred",
        "admission_hint": "pass",
        "score_reason": "明确表达展厅升级需求，未见立项",
        "evidences": [
            {
                "title": "示例报道",
                "summary": "提及展厅升级",
                "quote": "将升级企业展厅",
                "url": "https://news.example.com/a",
                "source_host": "news.example.com",
                "authority_tier": "unknown",
                "kept": True,
            }
        ],
        "discarded": [],
        "search_count": 2,
        "extract_count": 0,
    }
    data.update(overrides)
    return data


def test_request_rejects_blank_query() -> None:
    """空 query 校验失败。"""
    body = _sample_request_body()
    body["query"] = "  "
    with pytest.raises(ValidationError):
        HuayuanRadarEventRequest(**body)


def test_request_rejects_blank_company_name() -> None:
    """空公司名校验失败。"""
    body = _sample_request_body()
    body["context"]["company"]["company_name"] = " "
    with pytest.raises(ValidationError):
        HuayuanRadarEventRequest(**body)


def test_radar_event_context_search_limit_and_dedupe() -> None:
    """搜索次数与去重限制生效。"""
    data = build_radar_event_context_from_request(
        company_name="鼎捷数智",
        stock_code="300378",
        aliases=["鼎捷软件"],
        max_search_times=2,
        max_extract_times=1,
        max_results_per_search=5,
        max_extract_chars=1000,
        event_job_id=1,
        trace_id="t1",
    )
    ok, _ = data.can_search("鼎捷数智 展厅")
    assert ok
    data.mark_searched("鼎捷数智 展厅")
    ok2, reason2 = data.can_search("鼎捷数智 展厅")
    assert not ok2
    assert "已搜索" in reason2
    data.mark_searched("鼎捷数智 体验中心")
    ok3, reason3 = data.can_search("第三个")
    assert not ok3
    assert "上限" in reason3


def test_authority_tier_and_subject_match() -> None:
    """主机权威档与主体关键词匹配。"""
    assert extract_source_host("https://www.cninfo.com.cn/new/disclosure") == "cninfo.com.cn"
    assert classify_authority_tier("https://www.cninfo.com.cn/x") == "regulator_or_exchange"
    assert classify_authority_tier("https://xxx.gov.cn/a") == "gov"
    assert classify_authority_tier("https://www.zhihu.com/q") == "ugc_or_noise"
    assert text_mentions_subject("鼎捷数智建设展厅", ["鼎捷数智", "300378"])
    assert not text_mentions_subject("无关公司展厅", ["鼎捷数智", "300378"])


def test_parse_radar_event_score_success() -> None:
    """合法 JSON 解析成功，并重算 total。"""
    text = json.dumps(_sample_score_json(total_score=99), ensure_ascii=False)
    result = parse_radar_event_score_from_ai_text(text)
    assert result.exhibition_related is True
    assert result.evidence_score == 60
    assert result.specificity_score == 10
    assert result.total_score == 70
    assert result.evidences[0].url.startswith("https://")


def test_parse_rejects_illegal_evidence_score() -> None:
    """非法连续分值应失败。"""
    text = json.dumps(_sample_score_json(evidence_score=70), ensure_ascii=False)
    with pytest.raises(ValueError, match="evidence_score"):
        parse_radar_event_score_from_ai_text(text)


def test_parse_score_requires_evidence_url() -> None:
    """有分无 URL 应失败。"""
    text = json.dumps(
        _sample_score_json(
            evidences=[{"title": "无链接", "quote": "x", "url": "", "kept": True}]
        ),
        ensure_ascii=False,
    )
    with pytest.raises(ValueError, match="有分必有据"):
        parse_radar_event_score_from_ai_text(text)


def test_parse_unrelated_clears_scores() -> None:
    """不准入时清空分数。"""
    text = json.dumps(
        _sample_score_json(
            exhibition_related=False,
            evidence_score=25,
            specificity_score=5,
            total_score=30,
            evidences=[],
        ),
        ensure_ascii=False,
    )
    result = parse_radar_event_score_from_ai_text(text)
    assert result.exhibition_related is False
    assert result.total_score is None
    assert result.evidence_score is None
    assert result.admission_hint == "reject_unrelated"


def test_route_success_with_mocked_flow() -> None:
    """路由成功路径（mock Flow）。"""
    app = FastAPI()
    app.include_router(radar_event_router, prefix="/api/v1")
    client = TestClient(app)

    ai_payload = json.dumps(_sample_score_json(), ensure_ascii=False)
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={"flow_msgs": [AIMessage(content=ai_payload)]}
    )

    with patch(
        "backend.app.api.routes.huayuan_radar_event.FlowManager.get_flow",
        return_value=mock_graph,
    ), patch(
        "backend.app.api.routes.huayuan_radar_event.create_langfuse_handler",
        return_value=None,
    ):
        resp = client.post("/api/v1/huayuan/radar-event-score", json=_sample_request_body())

    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_id"] == "b" * 32
    assert body["radar_event_score"]["total_score"] == 70
    assert body["radar_event_score"]["evidences"][0]["url"]
    mock_graph.ainvoke.assert_awaited()


def test_route_parse_failure_returns_500() -> None:
    """模型输出非法分值时路由返回 500。"""
    app = FastAPI()
    app.include_router(radar_event_router, prefix="/api/v1")
    client = TestClient(app)

    bad_payload = json.dumps(_sample_score_json(evidence_score=68), ensure_ascii=False)
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={"flow_msgs": [AIMessage(content=bad_payload)]}
    )

    with patch(
        "backend.app.api.routes.huayuan_radar_event.FlowManager.get_flow",
        return_value=mock_graph,
    ), patch(
        "backend.app.api.routes.huayuan_radar_event.create_langfuse_handler",
        return_value=None,
    ):
        resp = client.post("/api/v1/huayuan/radar-event-score", json=_sample_request_body())

    assert resp.status_code == 500
    assert "radar_event_score" in resp.json()["detail"]


def test_flow_key_constant() -> None:
    """流程 key 与配置目录一致。"""
    assert HUAYUAN_RADAR_EVENT_FLOW_KEY == "huayuan_radar_event_agent"
