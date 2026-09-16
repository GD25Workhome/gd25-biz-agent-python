"""
华院规则二：按 doc_id 加载知识库新闻正文工具（按需拉全文）

回调 exhibition：
GET {document_tool_base_url}/radar/agent/tool/news-document/get?id=&maxChars=&companyId=

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md` §3.3 / §5
        与 03-子模块2-使用链路.md T2.4：
  - 白名单 = **本次 gather 从 Milvus 召回的 doc_ids**（请求级 contextvars，防乱拉）
  - `max_load_times` 默认 3、单次 `maxChars` 默认 12000（工具内固定）
  - 与画像侧 `huayuan_document_tool.py`（load_document_by_file_id）同构，互不影响
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

from backend.domain.tools.decorator import register_tool
from backend.domain.tools.huayuan_radar_event_context import (
    get_huayuan_radar_event_context,
)

logger = logging.getLogger(__name__)

# 工具 HTTP 超时（秒）
_HTTP_TIMEOUT_SEC = 10.0
# 环境变量兜底基址（请求 context 优先，与画像工具共用同一基址配置）
_ENV_BASE_URL_KEY = "HUAYUAN_DOCUMENT_TOOL_BASE_URL"


def _error_payload(message: str, **extra: Any) -> str:
    """将错误信息序列化为工具 Observation JSON 字符串。"""
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


@register_tool
async def load_news_document(doc_id: str) -> str:
    """
    按 doc_id 从公司新闻知识库拉取该篇新闻正文（已截断）。

    仅允许加载**本次 gather 从知识库召回的 doc_id**（briefs 中 tool_name=knowledge_base
    且带 doc_id 的条目）；受 max_load_times 限制（默认 3 次）。用于核对证据原文、
    补足摘要未覆盖的细节，不得据此编造内容。

    Args:
        doc_id: 知识库文档 ID（≡ radar_company_news_document.id，与 Milvus doc_id 一致）

    Returns:
        JSON 字符串（成功或失败均返回可读结构）
    """
    # 1. 读取请求级上下文（雷达事件专属）
    ctx = get_huayuan_radar_event_context()
    if ctx is None:
        return _error_payload("规则二上下文未初始化，无法加载知识库正文")

    knowledge = ctx.knowledge
    did = str(doc_id).strip()
    allowed, reason = knowledge.can_load(did)
    if not allowed:
        return _error_payload(
            reason,
            doc_id=did,
            load_count=knowledge.load_count,
            max_load_times=knowledge.max_load_times,
        )

    base_url = (knowledge.document_tool_base_url or "").strip().rstrip("/")
    if not base_url:
        base_url = (os.getenv(_ENV_BASE_URL_KEY) or "").strip().rstrip("/")
    if not base_url:
        return _error_payload(
            "缺少 document_tool_base_url，且未配置环境变量 "
            f"{_ENV_BASE_URL_KEY}",
            doc_id=did,
        )

    # 2. 组装工具 URL（联调免登录，不附加鉴权 Header）
    url = f"{base_url}/radar/agent/tool/news-document/get"
    params: Dict[str, Any] = {"id": did, "maxChars": knowledge.max_chars}
    if ctx.company_id is not None:
        params["companyId"] = ctx.company_id

    # 先占位计数，避免并发/循环内超限；HTTP 失败仍计一次，防止死循环刷外部
    knowledge.mark_loaded(did)

    try:
        # 3. 调用 exhibition 新闻文档工具
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SEC) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            body = resp.json()
    except httpx.TimeoutException:
        logger.warning(f"加载新闻正文超时: doc_id={did}, url={url}")
        return _error_payload("加载新闻正文超时", doc_id=did, url=url)
    except Exception as e:
        logger.warning(f"加载新闻正文失败: doc_id={did}, err={e}", exc_info=True)
        return _error_payload(f"加载新闻正文失败: {e}", doc_id=did, url=url)

    # 4. 兼容 yudao 风格 {code, data} 与直接 data
    data: Optional[Dict[str, Any]] = None
    if isinstance(body, dict):
        code = body.get("code")
        if code is not None and str(code) not in ("0", "200"):
            # yudao 业务错误（如文档不存在）通常 HTTP 200 + code!=0
            return _error_payload(
                f"知识库文档不可用: {body.get('msg') or body.get('message') or code}",
                doc_id=did,
                code=code,
            )
        if isinstance(body.get("data"), dict):
            data = body["data"]
        else:
            data = body

    if not isinstance(data, dict):
        return _error_payload("工具响应格式异常", doc_id=did, raw_type=str(type(body)))

    content = str(data.get("content") or "")
    result = {
        "ok": True,
        "doc_id": str(data.get("docId") or data.get("doc_id") or did),
        "title": data.get("title") or "",
        "source_type": data.get("sourceType") or data.get("source_type"),
        "source_level": data.get("sourceLevel") or data.get("source_level"),
        "published_at": data.get("publishedAt") or data.get("published_at"),
        "url": data.get("url") or "",
        "content": content,
        "truncated": bool(data.get("truncated", False)),
        "char_count": data.get("charCount")
        or data.get("char_count")
        or len(content),
        "has_full_text": (
            data.get("hasFullText") if "hasFullText" in data else data.get("has_full_text")
        ),
        "load_count": knowledge.load_count,
        "max_load_times": knowledge.max_load_times,
    }
    logger.info(
        f"[华院工具] 加载知识库新闻成功 doc_id={did}, chars={result['char_count']}, "
        f"truncated={result['truncated']}, load_count={knowledge.load_count}/"
        f"{knowledge.max_load_times}"
    )
    return json.dumps(result, ensure_ascii=False)
