"""
华院：按 doc_id 从公司新闻知识库直读 MySQL 正文（按需拉全文）。

白名单 = 本次 gather 召回的 doc_ids（雷达事件 / 画像 contextvars）。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple

from backend.domain.knowledge.news_document_read import load_document_for_agent
from backend.domain.tools.decorator import register_tool
from backend.domain.tools.huayuan_portrait_context import get_huayuan_portrait_context
from backend.domain.tools.huayuan_radar_event_context import (
    get_huayuan_radar_event_context,
)

logger = logging.getLogger(__name__)


def _error_payload(message: str, **extra: Any) -> str:
    """将错误信息序列化为工具 Observation JSON 字符串。"""
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _resolve_whitelist_loader() -> Tuple[Optional[Any], Optional[int], str]:
    """
        解析当前请求的加载上下文（雷达优先，其次画像）。

        Returns:
            (state对象含 can_load/mark_loaded/max_chars, company_id, 场景名)
    """
    portrait_ctx = get_huayuan_portrait_context()
    if portrait_ctx is not None:
        return portrait_ctx, portrait_ctx.company_id, "portrait"

    radar_ctx = get_huayuan_radar_event_context()
    if radar_ctx is not None:
        return radar_ctx.knowledge, radar_ctx.company_id, "radar_event"

    return None, None, ""


@register_tool
async def load_news_document(doc_id: str) -> str:
    """
    按 doc_id 从公司新闻知识库拉取该篇新闻正文（MySQL 直读，已截断）。

    仅允许加载**本次 gather 召回白名单**内的 doc_id；受 max_load_times 限制。

    Args:
        doc_id: 知识库文档 ID（≡ radar_company_news_document.id）

    Returns:
        JSON 字符串（成功或失败均返回可读结构）
    """
    loader, company_id, scene = _resolve_whitelist_loader()
    if loader is None:
        return _error_payload("未初始化华院上下文，无法加载知识库正文")

    did = str(doc_id).strip()
    allowed, reason = loader.can_load(did)
    if not allowed:
        return _error_payload(
            reason,
            doc_id=did,
            load_count=getattr(loader, "load_count", 0),
            max_load_times=getattr(loader, "max_load_times", 0),
        )

    if company_id is None:
        return _error_payload("缺少 company_id，无法校验文档归属", doc_id=did)

    max_chars = int(getattr(loader, "max_chars", 12000) or 12000)
    loader.mark_loaded(did)

    result = await load_document_for_agent(did, company_id, max_chars=max_chars)
    if not result.get("ok"):
        return json.dumps(result, ensure_ascii=False)

    portrait_ctx = get_huayuan_portrait_context()
    if portrait_ctx is not None and scene == "portrait":
        portrait_ctx.remember_loaded_content(did, str(result.get("content") or ""))

    radar_ctx = get_huayuan_radar_event_context()
    if radar_ctx is not None and scene == "radar_event":
        radar_ctx.knowledge.remember_loaded_content(did, str(result.get("content") or ""))

    result["load_count"] = loader.load_count
    result["max_load_times"] = loader.max_load_times
    result["source_type"] = "knowledge_base"
    logger.info(
        "[load_news_document] scene=%s doc_id=%s chars=%s truncated=%s load=%s/%s",
        scene,
        did,
        result.get("char_count"),
        result.get("truncated"),
        loader.load_count,
        loader.max_load_times,
    )
    return json.dumps(result, ensure_ascii=False)
