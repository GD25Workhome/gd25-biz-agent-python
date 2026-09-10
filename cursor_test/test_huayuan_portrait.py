"""
华院画像 /portrait 单元测试

覆盖：Schema、上下文限流、portrait 解析补齐、路由 mock 成功/解析失败。
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
    ensure_all_dimensions,
    parse_portrait_from_ai_text,
    router as portrait_router,
)
from backend.app.api.schemas.huayuan_portrait import (
    REQUIRED_DIM_CODES,
    HuayuanPortraitRequest,
    PortraitDimension,
    PortraitResult,
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
            "file_ids": ["1", "7"],
            "file_metas": [{"file_id": "7", "title": "公告", "summary": "摘要"}],
            "stats": {"doc_count_12m": 20},
            "max_load_times": 3,
            "document_tool_base_url": "http://127.0.0.1:38080/admin-api",
        },
        "trace_id": "a" * 32,
    }


def test_request_rejects_blank_query() -> None:
    """空 query 校验失败。"""
    body = _sample_request_body()
    body["query"] = "  "
    with pytest.raises(ValidationError):
        HuayuanPortraitRequest(**body)


def test_portrait_context_whitelist_and_dedupe() -> None:
    """白名单与去重限制生效。"""
    data = build_portrait_context_from_request(
        file_ids=["1", "7"],
        max_load_times=2,
        max_chars=100,
        document_tool_base_url="http://x",
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


def test_parse_portrait_and_fill_missing_dims() -> None:
    """解析成功后补齐缺失五维（抄 prefill）。"""
    text = json.dumps(
        {
            "dimensions": [
                {
                    "code": "biz_complexity",
                    "tier": "medium",
                    "fact_status": "inferred",
                    "evidence": [{"ref_id": 7, "quote": "产品线较复杂"}],
                },
                {
                    "code": "intel_potential",
                    "tier": "weak_or_unknown",
                    "fact_status": "unknown",
                    "missing_reason": "无数字化证据",
                },
            ],
            "loaded_file_ids": ["7"],
            "discarded_file_ids": [],
            "load_count": 1,
        },
        ensure_ascii=False,
    )
    prefill = {
        "budget": {"tier": "stronger"},
        "benchmark": {"tier": "stronger"},
        "update_freq": {"tier": "strong"},
    }
    portrait = parse_portrait_from_ai_text(text, prefill)
    codes = [d.code for d in portrait.dimensions]
    assert codes == REQUIRED_DIM_CODES
    by_code = {d.code: d for d in portrait.dimensions}
    assert by_code["budget"].tier == "stronger"
    assert by_code["biz_complexity"].tier == "medium"


def test_parse_portrait_failure_raises() -> None:
    """无法解析时抛 ValueError（路由应转 500）。"""
    with pytest.raises(ValueError):
        parse_portrait_from_ai_text("这不是JSON", None)


def test_ensure_all_dimensions_from_empty() -> None:
    """空 dimensions 全量补齐。"""
    portrait = ensure_all_dimensions(PortraitResult(dimensions=[]), None)
    assert len(portrait.dimensions) == 5
    assert all(d.tier == "weak_or_unknown" for d in portrait.dimensions)


@pytest.mark.asyncio
async def test_load_document_tool_respects_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """工具在无上下文或超限时返回错误 JSON。"""
    from backend.domain.tools import huayuan_document_tool as tool_mod

    # 无上下文
    out = await tool_mod.load_document_by_file_id.ainvoke({"file_id": "1"})
    payload = json.loads(out)
    assert payload["ok"] is False

    data = HuayuanPortraitContextData(
        allowed_file_ids={"1"},
        max_load_times=1,
        max_chars=100,
        document_tool_base_url="http://example.test/admin-api",
    )

    class _FakeResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "code": 0,
                "data": {
                    "fileId": "1",
                    "title": "t",
                    "content": "hello",
                    "truncated": False,
                    "charCount": 5,
                    "hasFullText": True,
                },
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            return _FakeResp()

    monkeypatch.setattr(tool_mod.httpx, "AsyncClient", _FakeClient)

    with HuayuanPortraitContext(data):
        out_ok = await tool_mod.load_document_by_file_id.ainvoke({"file_id": "1"})
        out_dup = await tool_mod.load_document_by_file_id.ainvoke({"file_id": "1"})

    assert json.loads(out_ok)["ok"] is True
    assert json.loads(out_dup)["ok"] is False


def test_portrait_api_success() -> None:
    """路由成功路径：mock 流程图返回合法 JSON。"""
    app = FastAPI()
    app.include_router(portrait_router, prefix="/api/v1")

    ai_payload = {
        "dimensions": [
            {"code": c, "tier": "medium", "fact_status": "inferred", "evidence": []}
            for c in REQUIRED_DIM_CODES
        ],
        "loaded_file_ids": [],
        "discarded_file_ids": [],
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
    assert len(data["portrait"]["dimensions"]) == 5
    mock_get.assert_called_once_with(HUAYUAN_PORTRAIT_FLOW_KEY)


def test_portrait_api_parse_failure_returns_500() -> None:
    """模型乱输出时 R1-a：HTTP 500。"""
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
