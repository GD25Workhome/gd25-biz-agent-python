"""
Milvus 向量化辅助（stub 摘要 / full 正文）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from backend.domain.news_content.pipeline import NewsContentProcessor, build_summary
from backend.infrastructure.llm.huayuan_embedding_client import HuayuanEmbeddingClient
from backend.infrastructure.milvus.radar_news_chunk_store import get_milvus_chunk_store

log = logging.getLogger("radar_kb.embed")


def _run_async(coro):
    """在同步调度器里跑 async 协程。"""
    return asyncio.run(coro)


async def _embed_stub_async(
    *,
    document_id: int,
    company_id: int,
    title: Optional[str],
    summary: Optional[str],
    url: str,
    source_kind: str,
    worker_id: str,
) -> bool:
    """
        将 stub 摘要写入单 chunk（content_grade=stub）。

        复用进程级 Milvus 单例，避免每篇文档新建客户端并重复 ensure collection。
    """
    text = (summary or title or "").strip()
    if not text:
        return False
    embed_text = f"{(title or '').strip()}\n{text}".strip()
    # 进程内单例：首次写入会 ensure，后续文档短路
    store = get_milvus_chunk_store()
    embedder = HuayuanEmbeddingClient()
    try:
        vectors = await embedder.embed_texts([embed_text])
        if not vectors:
            return False
        await store.delete_by_doc_id_async(int(document_id))
        await store.upsert_chunks_async(
            [
                {
                    "doc_id": int(document_id),
                    "company_id": int(company_id),
                    "chunk_index": 0,
                    "chunk_count": 1,
                    "char_start": 0,
                    "char_end": len(text),
                    "title": title or "",
                    "summary": build_summary(text),
                    "url": url,
                    "embed_text": embed_text,
                    "embedding": vectors[0],
                    "content_grade": "stub",
                    "source_kind": source_kind,
                }
            ]
        )
        log.info(
            "stub 向量写入成功 document_id=%s source_kind=%s worker=%s",
            document_id,
            source_kind,
            worker_id,
        )
        return True
    except Exception as exc:
        log.warning("stub 向量失败 document_id=%s err=%s", document_id, exc)
        return False
    finally:
        # 不关闭 Milvus 单例；仅释放本轮 embedding HTTP 客户端
        await embedder.aclose()


def embed_stub_document(
    *,
    document_id: int,
    company_id: int,
    title: Optional[str],
    summary: Optional[str],
    url: str,
    source_kind: str,
    worker_id: str,
) -> bool:
    """
    同步门面：发现后置 stub 摘要入 Milvus。

    Returns:
        是否写入成功
    """
    return _run_async(
        _embed_stub_async(
            document_id=document_id,
            company_id=company_id,
            title=title,
            summary=summary,
            url=url,
            source_kind=source_kind,
            worker_id=worker_id,
        )
    )


def embed_full_document(
    *,
    document_id: int,
    company_id: int,
    title: Optional[str],
    content_text: Optional[str],
    url: str,
    source_kind: str,
    worker_id: str,
) -> tuple[int, Optional[str]]:
    """
    正文成功后全量切分 embedding（带 content_grade=full）。

    Returns:
        (embed_status, error_message)
    """
    processor = NewsContentProcessor(worker_id=worker_id)

    async def _go():
        try:
            return await processor._embed_and_store(
                document_id=document_id,
                company_id=company_id,
                title=title,
                content_text=content_text,
                url=url,
                content_grade="full",
                source_kind=source_kind,
            )
        finally:
            await processor.aclose()

    return _run_async(_go())
