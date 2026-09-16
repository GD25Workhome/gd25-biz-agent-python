"""
新闻正文切分：固定字符滑窗 + 重叠（策略 C / V2）。

设计文档：ai_docs/26091607-新闻知识库全文切分与召回策略C设计.md §2
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# 末段过短则尝试并入上一段
_MIN_TAIL_CHARS = 40


@dataclass(frozen=True)
class EmbedChunk:
    """
        单段待嵌入文本。

        Attributes:
            index: 从 0 起的段序号
            text: 实际送入 embedding 的文本（可含 title 前缀）
            char_start: 相对正文的起始下标（不含 title）
            char_end: 相对正文的结束下标（不含 title）；仅 title 时为 0
            body_piece: 不含 title 前缀的正文片段（仅 title 时为空串）
    """

    index: int
    text: str
    char_start: int
    char_end: int
    body_piece: str


@dataclass(frozen=True)
class SplitEmbedResult:
    """
        切分结果。

        Attributes:
            chunks: 段列表；空表示标题与正文皆空
            truncated: 是否因 MAX_PER_DOC 截断了正文尾部
    """

    chunks: list[EmbedChunk]
    truncated: bool


def _compose_embed_text(title: str, body_piece: str) -> str:
    """组装单段嵌入文本：有 title 则 `{title}\\n{piece}`。"""
    if title and body_piece:
        return f"{title}\n{body_piece}"
    return title or body_piece


def split_embed_chunks(
    title: Optional[str],
    content_text: Optional[str],
    *,
    chunk_size: int,
    chunk_overlap: int,
    max_per_doc: int,
) -> SplitEmbedResult:
    """
        将标题 + 全文切成固定窗口的嵌入段。

        Args:
            title: 标题（可空）
            content_text: 正文（可空）
            chunk_size: 正文窗长（不含 title）
            chunk_overlap: 相邻窗重叠字符数
            max_per_doc: 单篇最大段数

        Returns:
            SplitEmbedResult；chunks 为空表示无法嵌入
    """
    # 1. 规范化入参
    title_text = (title or "").strip()
    body = (content_text or "").strip()
    size = max(1, int(chunk_size))
    overlap = max(0, min(int(chunk_overlap), size - 1))
    max_chunks = max(1, int(max_per_doc))
    step = max(1, size - overlap)

    if not body and not title_text:
        return SplitEmbedResult(chunks=[], truncated=False)

    # 2. 仅有标题
    if not body:
        return SplitEmbedResult(
            chunks=[
                EmbedChunk(
                    index=0,
                    text=title_text,
                    char_start=0,
                    char_end=0,
                    body_piece="",
                )
            ],
            truncated=False,
        )

    # 3. 滑窗切分
    raw: list[tuple[int, int, str]] = []
    start = 0
    while start < len(body) and len(raw) < max_chunks:
        end = min(len(body), start + size)
        piece = body[start:end]
        raw.append((start, end, piece))
        if end >= len(body):
            break
        start += step

    truncated = bool(raw) and raw[-1][1] < len(body)
    if truncated:
        logger.warning(
            "[chunking] 正文超长已截断 body_len=%d max_per_doc=%d covered_end=%d",
            len(body),
            max_chunks,
            raw[-1][1] if raw else 0,
        )

    # 4. 末段过短则并入上一段（合并后正文 ≤ chunk_size）
    if len(raw) >= 2:
        last_start, last_end, last_piece = raw[-1]
        if len(last_piece) < _MIN_TAIL_CHARS:
            prev_start, _prev_end, prev_piece = raw[-2]
            merged = prev_piece + last_piece
            # 注意：滑窗有重叠时 last 与 prev 可能重叠，不能简单拼接；
            # 用区间 [prev_start, last_end) 从正文重切，避免重复字符
            merged_from_body = body[prev_start:last_end]
            if len(merged_from_body) <= size:
                raw[-2] = (prev_start, last_end, merged_from_body)
                raw.pop()
            elif len(merged) <= size and not _ranges_overlap(
                prev_start, _prev_end, last_start, last_end
            ):
                raw[-2] = (prev_start, last_end, merged)
                raw.pop()

    # 5. 组装 EmbedChunk
    chunks: list[EmbedChunk] = []
    for index, (char_start, char_end, piece) in enumerate(raw):
        chunks.append(
            EmbedChunk(
                index=index,
                text=_compose_embed_text(title_text, piece),
                char_start=char_start,
                char_end=char_end,
                body_piece=piece,
            )
        )
    return SplitEmbedResult(chunks=chunks, truncated=truncated)


def _ranges_overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
    """判断半开区间 [a0,a1) 与 [b0,b1) 是否相交。"""
    return a0 < b1 and b0 < a1


def strip_title_prefix(embed_text: str, title: Optional[str]) -> str:
    """
        从 embed_text 去掉标题前缀，得到正文片段（供 brief.quote）。

        Args:
            embed_text: 含可选 `{title}\\n` 前缀的嵌入文本
            title: 文档标题

        Returns:
            正文片段；无法剥离时返回原文本去空白
    """
    text = str(embed_text or "")
    title_text = (title or "").strip()
    if title_text and text.startswith(title_text + "\n"):
        return text[len(title_text) + 1 :]
    return text.strip()


__all__ = [
    "EmbedChunk",
    "SplitEmbedResult",
    "split_embed_chunks",
    "strip_title_prefix",
]
