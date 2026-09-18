"""
华院画像 /portrait 单元测试
"""
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

from backend.app.api.routes.huayuan_portrait import (
    HUAYUAN_PORTRAIT_FLOW_KEY,
    parse_portrait_from_ai_text,
    router as portrait_router,
)
from backend.app.api.schemas.huayuan_portrait import (
    REQUIRED_DIM_CODES,
    HuayuanPortraitRequest,
)
from backend.domain.tools.huayuan_portrait_context import (
    HuayuanPortraitContext,
    HuayuanPortraitContextData,
    build_portrait_context_from_request,
)


def _sample_request_body() -> dict:
    return {
        "query": "请按华院五维画像标准评分：只输出候选档位",
        "context": {
            "profile_job_id": 3,
            "rule_version": "profile-v1",
            "company": {"company_id": 5556, "company_name": "中科美菱", "revenue_yi": 2.95},
            "rule_prefill": {
                "budget": {"tier": "stronger", "fact_status": "confirmed"},
                "benchmark": {"tier": "stronger", "fact_status": "confirmed"},
                "update_freq": {"tier": "strong", "fact_status": "inferred"},
            },
            "knowledge": {"enabled": True, "max_docs": 12},
            "candidate_docs": [
                {"doc_id": 9001, "title": "公告", "summary": "摘要", "content_grade": "full"}
            ],
            "max_load_times": 3,
        },
        "trace_id": "a" * 32,
    }


def test_request_rejects_blank_query() -> None:
    """空 query 校验失败。"""
    body = _sample_request_body()
    body["query"] = "  "
    with pytest.raises(ValidationError):
        HuayuanPortraitRequest(**body)


def test_portrait_context_empty_whitelist_rejects() -> None:
    """空白名单拒绝 load。"""
    data = build_portrait_context_from_request(
        company_id=1,
        allowed_doc_ids=[],
        max_load_times=2,
        max_chars=100,
        max_docs=20,
        knowledge_enabled=True,
        prefer_source_kinds=[],
        profile_job_id=3,
        trace_id="t1",
    )
    ok, reason = data.can_load("7")
    assert not ok
    assert "白名单为空" in reason


def test_portrait_context_whitelist_and_dedupe() -> None:
    """白名单与去重限制生效。"""
    data = build_portrait_context_from_request(
        company_id=1,
        allowed_doc_ids=["1", "7"],
        max_load_times=2,
        max_chars=100,
        max_docs=20,
        knowledge_enabled=True,
        prefer_source_kinds=[],
        profile_job_id=3,
        trace_id="t1",
    )
    ok, _ = data.can_load("7")
    assert ok
    data.mark_loaded("7")
    ok2, reason2 = data.can_load("7")
    assert not ok2
    assert "已加载" in reason2
    ok3, reason3 = data.can_load("99")
    assert not ok3
    assert "白名单" in reason3


def test_parse_portrait_score_items_and_fill() -> None:
    """解析 score_items 并补齐缺失维。"""
    text = json.dumps(
        {
            "score_items": [
                {
                    "code": "biz_complexity",
                    "tier": "medium",
                    "fact_status": "inferred",
                    "score_reason": "业务条线较多，展陈表达需求中等。",
                    "citations": [
                        {
                            "source_type": "knowledge_base",
                            "doc_id": 7,
                            "content_grade": "full",
                            "quote": "产品线较复杂",
                            "cite_reason": "说明业务复杂度",
                        }
                    ],
                },
            ],
            "loaded_doc_ids": ["7"],
            "load_count": 1,
        },
        ensure_ascii=False,
    )
    prefill = {
        "budget": {"tier": "stronger"},
        "benchmark": {"tier": "stronger"},
        "update_freq": {"tier": "strong"},
    }
    portrait = parse_portrait_from_ai_text(text, prefill, loaded_content={"7": "产品线较复杂"})
    codes = [d.code for d in portrait.score_items]
    assert codes == REQUIRED_DIM_CODES
    by_code = {d.code: d for d in portrait.score_items}
    assert by_code["budget"].tier == "stronger"
    assert by_code["biz_complexity"].tier == "medium"


def test_parse_portrait_rejects_legacy_dimensions() -> None:
    """dimensions 结构应失败。"""
    text = json.dumps({"dimensions": []}, ensure_ascii=False)
    with pytest.raises(ValueError, match="score_items"):
        parse_portrait_from_ai_text(text, None)


@pytest.mark.asyncio
async def test_load_news_document_respects_portrait_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """load_news_document 走画像白名单与 MySQL 读。"""
    from backend.domain.tools import load_news_document_tool as tool_mod

    out = await tool_mod.load_news_document.ainvoke({"doc_id": "1"})
    assert json.loads(out)["ok"] is False

    data = HuayuanPortraitContextData(
        company_id=100,
        allowed_doc_ids={"1"},
        max_load_times=1,
        max_chars=100,
    )

    async def _fake_load(doc_id, company_id, max_chars=12000):  # noqa: ANN001
        return {
            "ok": True,
            "doc_id": doc_id,
            "content": "hello",
            "truncated": False,
            "content_grade": "full",
            "has_full_text": True,
            "title": "t",
            "url": "https://x",
            "source_kind": "cninfo",
            "evidence_strength": "full",
            "char_count": 5,
        }

    monkeypatch.setattr(tool_mod, "load_document_for_agent", _fake_load)

    with HuayuanPortraitContext(data):
        out_ok = await tool_mod.load_news_document.ainvoke({"doc_id": "1"})
        out_dup = await tool_mod.load_news_document.ainvoke({"doc_id": "1"})

    assert json.loads(out_ok)["ok"] is True
    assert json.loads(out_dup)["ok"] is False


def test_portrait_api_success() -> None:
    """路由成功路径：mock 流程图返回 score_items。"""
    app = FastAPI()
    app.include_router(portrait_router, prefix="/api/v1")

    ai_payload = {
        "score_items": [
            {
                "code": c,
                "tier": "medium",
                "fact_status": "inferred",
                "score_reason": "测试占位理由至少八字以上。",
                "citations": [],
            }
            for c in REQUIRED_DIM_CODES
        ],
        "loaded_doc_ids": [],
        "load_count": 0,
    }
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={"flow_msgs": [AIMessage(content=json.dumps(ai_payload, ensure_ascii=False))]}
    )

    with patch(
        "backend.app.api.routes.huayuan_portrait.FlowManager.get_flow",
        return_value=mock_graph,
    ) as mock_get, patch(
        "backend.app.api.routes.huayuan_portrait.create_langfuse_handler",
        return_value=None,
    ):
        client = TestClient(app)
        resp = client.post("/api/v1/huayuan/portrait", json=_sample_request_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"] == "a" * 32
    assert len(data["portrait"]["score_items"]) == 5
    mock_get.assert_called_once_with(HUAYUAN_PORTRAIT_FLOW_KEY)
    assert HUAYUAN_PORTRAIT_FLOW_KEY == "huayuan_portrait_agent"


def test_portrait_api_parse_failure_returns_500() -> None:
    """模型乱输出时 HTTP 500。"""
    app = FastAPI()
    app.include_router(portrait_router, prefix="/api/v1")

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={"flow_msgs": [AIMessage(content="抱歉我不会 JSON")]}
    )

    with patch(
        "backend.app.api.routes.huayuan_portrait.FlowManager.get_flow",
        return_value=mock_graph,
    ), patch(
        "backend.app.api.routes.huayuan_portrait.create_langfuse_handler",
        return_value=None,
    ):
        client = TestClient(app)
        resp = client.post("/api/v1/huayuan/portrait", json=_sample_request_body())

    assert resp.status_code == 500
    assert "portrait" in resp.json()["detail"]
