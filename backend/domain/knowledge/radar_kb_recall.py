"""
Milvus 知识库双路召回（full + stub）。

仅使用 collection `radar_company_news_chunk`（经 get_milvus_store()）。
过滤：company_id + content_grade（full|stub）；可选 source_kind；禁止 source_level。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from backend.app.config import settings
from backend.domain.news_content.chunking import strip_title_prefix

logger = logging.getLogger(__name__)

# 与 gather brief 契约对齐
CONTENT_GRADES = ("full", "stub")


async def recall_chunks_for_query(
    query: str,
    *,
    company_id: int,
    top_k: int,
    source_kind: Optional[str] = None,
) -> Dict[str, Any]:
    """
        单条 query：embedding → Milvus full/stub 双路检索并合并 chunk。

        任何失败返回 ok=False，不抛异常。

        Args:
            query: 检索式
            company_id: 企业 ID（必填，防跨租户召回）
            top_k: 合并后保留的 chunk 上限
            source_kind: 可选，如 cninfo / news_html

        Returns:
            {"ok": bool, "query": str, "results": list[dict], "error": str}
    """
    payload: Dict[str, Any] = {
        "ok": False,
        "query": query,
        "results": [],
        "error": "",
    }
    q = str(query or "").strip()
    if not q:
        payload["error"] = "query 为空"
        return payload
    if company_id is None:
        payload["error"] = "缺少 company_id"
        return payload

    cap = max(1, min(128, int(top_k)))
    per_path = max(4, cap // 2)
    try:
        from backend.infrastructure.llm.huayuan_embedding_client import HuayuanEmbeddingClient
        from backend.infrastructure.milvus import get_milvus_store

        embedder = HuayuanEmbeddingClient()
        try:
            vector = await embedder.embed_one(q)
        finally:
            await embedder.aclose()
        store = get_milvus_store()
        search_kw: Dict[str, Any] = {"company_id": int(company_id), "top_k": per_path}
        if source_kind:
            search_kw["source_kind"] = str(source_kind).strip()
        full_hits = await store.search_async(
            vector, content_grade="full", **search_kw
        )
        stub_hits = await store.search_async(
            vector, content_grade="stub", **search_kw
        )
        merged = merge_chunk_hits(full_hits, stub_hits, top_k=cap)
        payload["ok"] = True
        payload["results"] = merged
        return payload
    except Exception as e:
        payload["error"] = f"{type(e).__name__}: {e}"
        logger.warning("[radar_kb_recall] query=%s 失败: %s", q[:40], payload["error"])
        return payload


def merge_chunk_hits(
    full_hits: Sequence[Dict[str, Any]] | None,
    stub_hits: Sequence[Dict[str, Any]] | None,
    *,
    top_k: int,
) -> List[Dict[str, Any]]:
    """
        合并 full/stub 两路 chunk 命中：同 chunk_id 取更高分，再按分降序截断。

        Args:
            full_hits: full 路结果
            stub_hits: stub 路结果
            top_k: 输出条数上限

        Returns:
            chunk 级 dict 列表（含 doc_id、score、content_grade 等）
    """
    merged: dict[str, dict[str, Any]] = {}
    for hit in list(full_hits or []) + list(stub_hits or []):
        if not isinstance(hit, dict):
            continue
        key = str(hit.get("chunk_id") or hit.get("doc_id") or "")
        if not key:
            continue
        prev = merged.get(key)
        if prev is None or float(hit.get("score") or 0) > float(prev.get("score") or 0):
            merged[key] = hit
    ranked = sorted(
        merged.values(),
        key=lambda h: float(h.get("score") or 0),
        reverse=True,
    )
    return ranked[: max(1, int(top_k))]


def chunk_hit_to_doc_brief(hit: Dict[str, Any], *, quote_max_chars: Optional[int] = None) -> Dict[str, Any]:
    """
        将单条 chunk 命中转为文档级 brief（供 gather / 画像 prompt）。

        Args:
            hit: Milvus 返回的 chunk 字段
            quote_max_chars: quote 截断长度；缺省用 KNOWLEDGE_BRIEF_QUOTE_MAX_CHARS

        Returns:
            doc_id, title, url, quote, content_grade, source_kind, score
    """
    limit = int(quote_max_chars or settings.KNOWLEDGE_BRIEF_QUOTE_MAX_CHARS)
    title = hit.get("title")
    quote_body = strip_title_prefix(str(hit.get("embed_text") or ""), title)
    quote = quote_body[:limit] if len(quote_body) > limit else quote_body
    return {
        "doc_id": str(hit.get("doc_id") or "").strip(),
        "title": title,
        "url": str(hit.get("url") or "").strip(),
        "quote": quote or None,
        "content_grade": hit.get("content_grade"),
        "source_kind": hit.get("source_kind"),
        "score": hit.get("score"),
        "chunk_index": hit.get("chunk_index"),
        "chunk_count": hit.get("chunk_count"),
        "summary": hit.get("summary"),
        "embed_text": hit.get("embed_text"),
    }


async def recall_doc_briefs_for_queries(
    queries: Sequence[str],
    *,
    company_id: int,
    top_k_per_query: int,
    source_kind: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
        多 query 并行召回，按 doc_id 保留最高分 chunk 并转为 doc brief。

        Args:
            queries: 检索式列表
            company_id: 企业 ID
            top_k_per_query: 每个 query 的 chunk top_k
            source_kind: 可选 Milvus 过滤

        Returns:
            (briefs 按 score 降序, 各 query 的原始 payload 列表)
    """
    import asyncio

    coros = [
        recall_chunks_for_query(
            q,
            company_id=company_id,
            top_k=top_k_per_query,
            source_kind=source_kind,
        )
        for q in queries
        if str(q or "").strip()
    ]
    if not coros:
        return [], []

    raw_results = await asyncio.gather(*coros, return_exceptions=True)
    payloads: List[Dict[str, Any]] = []
    best_by_doc: Dict[str, tuple[float, Dict[str, Any]]] = {}

    for item in raw_results:
        if isinstance(item, Exception):
            payloads.append({"ok": False, "error": str(item), "results": []})
            continue
        if not isinstance(item, dict):
            continue
        payloads.append(item)
        if not item.get("ok"):
            continue
        for hit in item.get("results") or []:
            if not isinstance(hit, dict):
                continue
            doc_id = str(hit.get("doc_id") or "").strip()
            if not doc_id:
                continue
            score = float(hit.get("score") or 0)
            prev = best_by_doc.get(doc_id)
            if prev is None or score > prev[0]:
                best_by_doc[doc_id] = (score, hit)

    briefs = [
        chunk_hit_to_doc_brief(hit)
        for _, hit in sorted(best_by_doc.values(), key=lambda x: x[0], reverse=True)
    ]
    return briefs, payloads
