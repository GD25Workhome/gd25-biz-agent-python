"""
新闻知识库切分与策略 C 合并逻辑单测。

设计文档：ai_docs/26091607-新闻知识库全文切分与召回策略C设计.md
"""
from __future__ import annotations

import sys
from pathlib import Path

# 仓库根目录入 path，便于直接 pytest
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.domain.flows.implementations.radar_evidence_gather_node import (
    EvidenceGatherNode,
)
from backend.domain.news_content.chunking import (
    split_embed_chunks,
    strip_title_prefix,
)


def test_split_empty() -> None:
    """标题与正文皆空 → 无 chunk。"""
    result = split_embed_chunks(
        None, None, chunk_size=1000, chunk_overlap=200, max_per_doc=50
    )
    assert result.chunks == []
    assert result.truncated is False


def test_split_title_only() -> None:
    """仅标题 → 单 chunk。"""
    result = split_embed_chunks(
        "标题A", "  ", chunk_size=1000, chunk_overlap=200, max_per_doc=50
    )
    assert len(result.chunks) == 1
    assert result.chunks[0].text == "标题A"
    assert result.chunks[0].body_piece == ""


def test_split_window_and_overlap() -> None:
    """滑窗步长 = size - overlap。"""
    body = "a" * 2500
    result = split_embed_chunks(
        "T", body, chunk_size=1000, chunk_overlap=200, max_per_doc=50
    )
    assert len(result.chunks) == 3
    assert result.chunks[0].char_start == 0
    assert result.chunks[0].char_end == 1000
    assert result.chunks[1].char_start == 800
    assert result.chunks[0].text.startswith("T\n")
    assert result.truncated is False


def test_split_max_per_doc_truncates() -> None:
    """超过 MAX 截断并标记 truncated。"""
    body = "x" * 10000
    result = split_embed_chunks(
        None, body, chunk_size=1000, chunk_overlap=200, max_per_doc=2
    )
    assert len(result.chunks) == 2
    assert result.truncated is True


def test_split_merge_short_tail() -> None:
    """末段过短且并入后不超过窗长时合并。"""
    # 窗 150、重叠 0：两段 100 + 20 → 合并成一段 120
    body = "a" * 100 + "b" * 20
    result = split_embed_chunks(
        None, body, chunk_size=150, chunk_overlap=0, max_per_doc=50
    )
    assert len(result.chunks) == 1
    assert result.chunks[0].body_piece == body
    assert result.chunks[0].char_end == 120


def test_strip_title_prefix() -> None:
    """剥离 title 前缀。"""
    assert strip_title_prefix("标题\n正文一段", "标题") == "正文一段"
    assert strip_title_prefix("无前缀正文", "标题") == "无前缀正文"


def test_can_attach_second_chunk_index_gap() -> None:
    """第二段要求 index 间隔 ≥2。"""
    best = {"chunk_index": 0}
    near = {"chunk_index": 1}
    far = {"chunk_index": 2}
    assert EvidenceGatherNode._can_attach_second_chunk(best, near, 0.9, 0.89) is False
    assert EvidenceGatherNode._can_attach_second_chunk(best, far, 0.9, 0.89) is True


def test_knowledge_brief_injects_quote() -> None:
    """brief.quote 来自 embed_text（去标题）。"""
    node = EvidenceGatherNode()
    hit = {
        "doc_id": 42,
        "title": "公司新闻",
        "summary": "摘要",
        "url": "https://example.com/a",
        "score": 0.88,
        "chunk_index": 1,
        "chunk_count": 3,
        "embed_text": "公司新闻\n这是命中的中段正文内容。",
    }
    brief = node._knowledge_brief(hit, "展厅", ["某某公司"])
    assert brief["doc_id"] == "42"
    assert brief["quote"] == "这是命中的中段正文内容。"
    assert "第 2/3 段" in brief["why_evidential"]
