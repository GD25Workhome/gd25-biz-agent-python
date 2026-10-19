"""DeepSeek 网页搜索 / 抓取工具单测（mock 传输；不连 DB、不打外网）。

覆盖：工具注册、缺 key 降级、请求体组装与条数收敛、结果归一、
HTTP 错误码映射、抓取截断、key 回退。
运行：`python cursor_test/test_deepseek_search_tool.py`（建议 py311_GD25_base 环境）。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.domain.tools import deepseek_search_tool as ds  # noqa: E402
from backend.domain.tools.registry import tool_registry  # noqa: E402


def _run(tool, payload: dict) -> dict:
    """调用注册后的工具（BaseTool.ainvoke）并解析其 JSON 输出。"""
    raw = asyncio.run(tool.ainvoke(payload))
    return json.loads(raw)


def _fake_transport(status: int, body):
    """构造一个记录调用参数的假 _post_json。"""
    calls = []

    async def _post(url, headers, payload, timeout):
        calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout})
        return status, body, ""

    return _post, calls


_SEARCH_BODY = {
    "results": [
        {
            "rerank_score": 2.4,
            "title": "某公司展厅建设招标公告",
            "url": "https://ex.com/tender",
            "snippet": "短摘要",
            "summary": "长摘要" * 200,
            "content": "正文" * 3000,
            "site_name": "示例财经",
            "site_icon": None,
            "date": "2026-06-01T00:00:00+00:00",
            "authority": 3,
        }
    ]
}


def test_registered():
    """两个工具已随模块导入自动注册。"""
    assert tool_registry.get_tool("deepseek_web_search") is not None
    assert tool_registry.get_tool("deepseek_fetch") is not None


def test_missing_key_degrades():
    """无 key 时返回错误 JSON，不抛异常。"""
    with patch.object(ds, "resolve_deepseek_key", return_value=None):
        out = _run(ds.deepseek_web_search, {"query": "测试公司 展厅"})
        out2 = _run(ds.deepseek_fetch, {"url": "https://ex.com/a"})
    assert out["ok"] is False and "DEEPSEEK_SEARCH_KEY" in out["error"]
    assert out2["ok"] is False


def test_search_success_and_normalize():
    """成功：请求体字段正确、结果按契约归一、content 截断。"""
    post, calls = _fake_transport(200, _SEARCH_BODY)
    with patch.object(ds, "resolve_deepseek_key", return_value="sk-test"), patch.object(
        ds, "_post_json", post
    ):
        out = _run(ds.deepseek_web_search, {"query": "测试公司 展厅", "need_content": True})

    assert out["ok"] is True and out["result_count"] == 1 and out["count"] == 10
    one = out["results"][0]
    assert one["title"] == "某公司展厅建设招标公告"
    assert one["url"] == "https://ex.com/tender"
    assert one["kept_hint"] is True
    assert one["authority"] == 3
    assert len(one["content"]) == ds._SEARCH_CONTENT_MAX  # 正文被截断

    sent = calls[0]["payload"]
    assert sent["query"] == "测试公司 展厅" and sent["need_content"] is True
    assert calls[0]["url"].endswith("/v1/tools/search")
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-test"


def test_count_clamp_and_ori_question():
    """条数收敛到 1–50；ori_question 透传且截断到 128。"""
    post, calls = _fake_transport(200, {"results": []})
    with patch.object(ds, "resolve_deepseek_key", return_value="sk"), patch.object(
        ds, "_post_json", post
    ):
        _run(ds.deepseek_web_search, {"query": "q", "count": 999})
        _run(ds.deepseek_web_search, {"query": "q", "count": 0, "ori_question": "x" * 200})
    assert calls[0]["payload"]["count"] == 50
    assert calls[1]["payload"]["count"] == 10
    assert len(calls[1]["payload"]["ori_question"]) == 128


def test_search_http_error_mapping():
    """401 → unauthorized；错误 message 从 OpenAI 兼容体取出。"""
    post, _ = _fake_transport(
        401, {"error": {"message": "Authentication Fails", "type": "authentication_error"}}
    )
    with patch.object(ds, "resolve_deepseek_key", return_value="sk"), patch.object(
        ds, "_post_json", post
    ):
        out = _run(ds.deepseek_web_search, {"query": "q"})
    assert out["ok"] is False
    assert out["error_code"] == "unauthorized" and out["http_status"] == 401
    assert out["error"] == "Authentication Fails"


def test_fetch_success_and_truncate():
    """抓取成功；超长正文截断到上限。"""
    post, calls = _fake_transport(200, {"title": "页面标题", "content": "a" * 20000})
    with patch.object(ds, "resolve_deepseek_key", return_value="sk"), patch.object(
        ds, "_post_json", post
    ):
        out = _run(ds.deepseek_fetch, {"url": "https://ex.com/article"})
    assert out["ok"] is True and out["title"] == "页面标题" and out["truncated"] is True
    assert out["content_length"] == ds._FETCH_CONTENT_MAX
    assert calls[0]["url"].endswith("/v1/tools/fetch")
    assert calls[0]["payload"] == {"url": "https://ex.com/article"}


def test_fetch_not_found_and_bad_url():
    """404 → not_found；非 http(s) URL 本地拒绝。"""
    post, _ = _fake_transport(404, {"error": {"message": "no content"}})
    with patch.object(ds, "resolve_deepseek_key", return_value="sk"), patch.object(
        ds, "_post_json", post
    ):
        out = _run(ds.deepseek_fetch, {"url": "https://ex.com/pdf.pdf"})
        bad = _run(ds.deepseek_fetch, {"url": "ftp://ex.com/a"})
    assert out["ok"] is False and out["error_code"] == "not_found"
    assert bad["ok"] is False and "http(s)" in bad["error"]


def test_key_fallback():
    """DEEPSEEK_SEARCH_KEY 缺省时回退 DEEPSEEK_API_KEY。"""
    import os

    old = {k: os.environ.get(k) for k in ("DEEPSEEK_SEARCH_KEY", "DEEPSEEK_API_KEY")}
    try:
        os.environ.pop("DEEPSEEK_SEARCH_KEY", None)
        os.environ["DEEPSEEK_API_KEY"] = "sk-fallback"
        with patch.object(ds, "_read_setting", side_effect=lambda n: os.environ.get(n)):
            assert ds.resolve_deepseek_key() == "sk-fallback"
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


if __name__ == "__main__":
    test_registered()
    test_missing_key_degrades()
    test_search_success_and_normalize()
    test_count_clamp_and_ori_question()
    test_search_http_error_mapping()
    test_fetch_success_and_truncate()
    test_fetch_not_found_and_bad_url()
    test_key_fallback()
    print("test_deepseek_search_tool: all passed")