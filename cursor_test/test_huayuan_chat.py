"""
华院联通聊天接口单元测试

覆盖：Schema 校验、回复提取、路由主路径（mock 流程图）。
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

# 保证可从仓库根目录导入 backend
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.app.api.routes.huayuan_chat import (
    HUAYUAN_FLOW_KEY,
    build_huayuan_initial_state,
    extract_response_text,
    router as huayuan_router,
)
from backend.app.api.schemas.huayuan_chat import HuayuanChatRequest


def test_huayuan_chat_request_rejects_blank_query() -> None:
    """query 为空或仅空白时应校验失败。"""
    with pytest.raises(ValidationError):
        HuayuanChatRequest(query="   ")


def test_huayuan_chat_request_strips_query() -> None:
    """query 应去除首尾空白。"""
    req = HuayuanChatRequest(query="  你好  ")
    assert req.query == "你好"


def test_build_huayuan_initial_state_minimal() -> None:
    """初始状态应包含当前消息且无历史。"""
    state = build_huayuan_initial_state("hello", "abc123")
    assert isinstance(state["current_message"], HumanMessage)
    assert state["current_message"].content == "hello"
    assert state["history_messages"] == []
    assert state["flow_msgs"] == []
    assert state["trace_id"] == "abc123"
    assert state["session_id"] == ""
    assert "current_date" in (state.get("prompt_vars") or {})


def test_extract_response_text_from_last_ai_message() -> None:
    """应从 flow_msgs 最后一条 AIMessage 取回复。"""
    result = {
        "flow_msgs": [
            AIMessage(content="第一句"),
            AIMessage(content="最终回复"),
        ]
    }
    assert extract_response_text(result) == "最终回复"


def test_extract_response_text_fallback_when_empty() -> None:
    """无 AI 消息时返回兜底文案。"""
    assert extract_response_text({"flow_msgs": []}) == "抱歉，我没有收到回复。"


def test_huayuan_chat_api_success() -> None:
    """
        路由成功路径：不依赖真实 LLM，mock FlowManager 与 Langfuse。
    """
    app = FastAPI()
    app.include_router(huayuan_router, prefix="/api/v1")

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={"flow_msgs": [AIMessage(content="联通成功")]}
    )

    with patch(
        "backend.app.api.routes.huayuan_chat.FlowManager.get_flow",
        return_value=mock_graph,
    ) as mock_get_flow, patch(
        "backend.app.api.routes.huayuan_chat.create_langfuse_handler",
        return_value=None,
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/huayuan/chat",
            json={"query": "你好", "trace_id": "t" * 32},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "联通成功"
    assert data["trace_id"] == "t" * 32
    mock_get_flow.assert_called_once_with(HUAYUAN_FLOW_KEY)
    mock_graph.ainvoke.assert_awaited()


def test_huayuan_chat_api_rejects_empty_query() -> None:
    """空 query 应返回 422。"""
    app = FastAPI()
    app.include_router(huayuan_router, prefix="/api/v1")
    client = TestClient(app)
    resp = client.post("/api/v1/huayuan/chat", json={"query": "  "})
    assert resp.status_code == 422


def test_huayuan_chat_api_flow_load_failure() -> None:
    """流程加载失败应返回 500。"""
    app = FastAPI()
    app.include_router(huayuan_router, prefix="/api/v1")

    with patch(
        "backend.app.api.routes.huayuan_chat.FlowManager.get_flow",
        side_effect=ValueError("流程定义不存在: huayuan_simple_agent"),
    ), patch(
        "backend.app.api.routes.huayuan_chat.create_langfuse_handler",
        return_value=None,
    ):
        client = TestClient(app)
        resp = client.post("/api/v1/huayuan/chat", json={"query": "你好"})

    assert resp.status_code == 500
    assert "流程加载失败" in resp.json()["detail"]
