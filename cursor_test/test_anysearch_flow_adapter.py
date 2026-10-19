"""AnySearch 华院薄适配层测试（mock 客户端；不连 DB、不打外网）。

验证：同名工具注册、配额、enrichment、抽取截断、输出字段契约。
运行：`python cursor_test/test_anysearch_flow_adapter.py`（建议 py311_GD25_base 环境）。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.domain.tools import anysearch_flow as flow  # noqa: E402
from backend.domain.tools.huayuan_radar_event_context import (  # noqa: E402
    HuayuanRadarEventContext,
    build_radar_event_context_from_request,
)
from backend.domain.tools.registry import tool_registry  # noqa: E402


class _FakeClient:
    """假客户端：search/extract 直接返回，不打外网。"""

    async def search(self, query: str, max_results: int = 0):
        return {
            "ok": True,
            "query": query,
            "results": [
                {"title": "某公司展厅招标", "url": "https://ex.com/a", "snippet": "含公司名", "content": "正文"}
            ],
            "result_count": 1,
        }

    async def extract(self, url: str):
        return {"ok": True, "url": url, "content": "x" * 5000}


def _ctx(**kw):
    """构造规则二请求上下文。"""
    defaults = dict(
        company_name="测试公司", stock_code="300000", aliases=[], max_bocha=0,
        max_anysearch=10, max_extract_times=5, max_results_per_search=5,
        max_extract_chars=12000, event_job_id=1, trace_id="t", company_id=1,
        knowledge_enabled=False,
    )
    defaults.update(kw)
    return build_radar_event_context_from_request(**defaults)


def _run(tool, payload):
    """在请求上下文内调用工具（BaseTool.ainvoke）。"""
    return asyncio.run(_invoke(tool, payload))


async def _invoke(tool, payload):
    return await tool.ainvoke(payload)


def test_tools_registered() -> None:
    """同名工具已注册。"""
    assert tool_registry.get_tool("anysearch_web_search") is not None
    assert tool_registry.get_tool("anysearch_extract") is not None


def test_search_enrich_and_contract() -> None:
    """成功搜索：字段契约 + enrichment。"""
    flow.get_client = lambda: _FakeClient()  # 打桩
    with HuayuanRadarEventContext(_ctx()):
        raw = _run(flow.anysearch_web_search, {"query": "测试公司 展厅", "max_results": 0})
    out = json.loads(raw)
    assert out["ok"] is True
    assert out["result_count"] == 1
    item = out["results"][0]
    assert item["source_host"] == "ex.com"
    assert item["kept_hint"] is True
    assert "authority_tier" in item and "subject_match" in item
    assert out["tool_name"] == "anysearch_web_search"
    assert out["anysearch_count"] == 1 and out["max_anysearch"] == 10


def test_search_quota_exceeded() -> None:
    """超过 max_anysearch → 本地拒（不调外部）。"""
    flow.get_client = lambda: _FakeClient()
    with HuayuanRadarEventContext(_ctx(max_anysearch=1)):
        first = json.loads(_run(flow.anysearch_web_search, {"query": "q1"}))
        second = json.loads(_run(flow.anysearch_web_search, {"query": "q2"}))
    assert first["ok"] is True
    assert second["ok"] is False and "上限" in second["error"]


def test_extract_truncate() -> None:
    """抽取超过 max_extract_chars → truncated=True。"""
    flow.get_client = lambda: _FakeClient()
    with HuayuanRadarEventContext(_ctx(max_extract_chars=100)):
        out = json.loads(_run(flow.anysearch_extract, {"url": "https://ex.com/a"}))
    assert out["ok"] is True
    assert out["truncated"] is True and len(out["content"]) == 100
    assert out["source_host"] == "ex.com"


def test_no_context() -> None:
    """无请求上下文 → 可读错误。"""
    out = json.loads(_run(flow.anysearch_web_search, {"query": "q"}))
    assert out["ok"] is False and "上下文未初始化" in out["error"]


def _run_all() -> None:
    """简易运行器。"""
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"全部通过：{len(tests)} 项")


if __name__ == "__main__":
    _run_all()