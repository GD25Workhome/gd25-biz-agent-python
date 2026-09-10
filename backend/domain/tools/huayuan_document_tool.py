"""
华院画像：按 file_id 加载证据正文工具

回调 exhibition：
GET {document_tool_base_url}/radar/agent/tool/document/get?id=...
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

from backend.domain.tools.decorator import register_tool
from backend.domain.tools.huayuan_portrait_context import get_huayuan_portrait_context

logger = logging.getLogger(__name__)

# 工具 HTTP 超时（秒）
_HTTP_TIMEOUT_SEC = 10.0
# 环境变量兜底基址（请求 context 优先）
_ENV_BASE_URL_KEY = "HUAYUAN_DOCUMENT_TOOL_BASE_URL"


def _error_payload(message: str, **extra: Any) -> str:
    """将错误信息序列化为工具 Observation JSON 字符串。"""
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


@register_tool
async def load_document_by_file_id(file_id: str) -> str:
    """
    根据证据 file_id 从业务服务加载文档正文（已截断）。

    仅允许加载本次画像请求白名单内的 file_id；受 max_load_times 限制。
    返回 JSON 字符串，含 title/content/truncated 等字段。

    Args:
        file_id: 证据文档 ID（对应 radar_raw_document.id）

    Returns:
        JSON 字符串（成功或失败均返回可读结构）
    """
    # 1. 读取请求级上下文
    ctx = get_huayuan_portrait_context()
    if ctx is None:
        return _error_payload("画像上下文未初始化，无法加载文档")

    fid = str(file_id).strip()
    allowed, reason = ctx.can_load(fid)
    if not allowed:
        return _error_payload(reason, file_id=fid, load_count=ctx.load_count)

    base_url = (ctx.document_tool_base_url or "").strip().rstrip("/")
    if not base_url:
        base_url = (os.getenv(_ENV_BASE_URL_KEY) or "").strip().rstrip("/")
    if not base_url:
        return _error_payload(
            "缺少 document_tool_base_url，且未配置环境变量 "
            f"{_ENV_BASE_URL_KEY}",
            file_id=fid,
        )

    # 2. 组装工具 URL（联调免登录，不附加鉴权 Header）
    url = f"{base_url}/radar/agent/tool/document/get"
    params: Dict[str, Any] = {"id": fid, "maxChars": ctx.max_chars}
    if ctx.profile_job_id is not None:
        params["jobId"] = ctx.profile_job_id

    # 先占位计数，避免并发/循环内超限；HTTP 失败仍计一次，防止死循环刷外部
    ctx.mark_loaded(fid)

    try:
        # 3. 调用 exhibition 文档工具
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SEC) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            body = resp.json()
    except httpx.TimeoutException:
        logger.warning(f"加载文档超时: file_id={fid}, url={url}")
        return _error_payload("加载文档超时", file_id=fid, url=url)
    except Exception as e:
        logger.warning(f"加载文档失败: file_id={fid}, err={e}", exc_info=True)
        return _error_payload(f"加载文档失败: {e}", file_id=fid, url=url)

    # 4. 兼容 yudao 风格 {code, data} 与直接 data
    data: Optional[Dict[str, Any]] = None
    if isinstance(body, dict):
        if isinstance(body.get("data"), dict):
            data = body["data"]
        else:
            data = body

    if not isinstance(data, dict):
        return _error_payload("工具响应格式异常", file_id=fid, raw_type=str(type(body)))

    result = {
        "ok": True,
        "file_id": str(data.get("fileId") or data.get("file_id") or fid),
        "title": data.get("title") or "",
        "source_type": data.get("sourceType") or data.get("source_type"),
        "published_at": data.get("publishedAt") or data.get("published_at"),
        "content": data.get("content") or "",
        "truncated": bool(data.get("truncated", False)),
        "char_count": data.get("charCount") or data.get("char_count") or len(str(data.get("content") or "")),
        "has_full_text": data.get("hasFullText") if "hasFullText" in data else data.get("has_full_text"),
        "load_count": ctx.load_count,
    }
    logger.info(
        f"[华院工具] 加载文档成功 file_id={fid}, chars={result['char_count']}, "
        f"load_count={ctx.load_count}"
    )
    return json.dumps(result, ensure_ascii=False)
