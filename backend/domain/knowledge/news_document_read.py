"""
Agent 侧直读 radar_company_news_document（白名单外的 company_id 校验在调用方）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

from backend.app.config import settings
# 与 news_content/repository 一致：deleted 为 bit(1)
_NOT_DELETED = "deleted = b'0'"
from backend.infrastructure.database.mysql_connection import (
    ExhibitionMysqlError,
    query_one,
    run_db,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 12000


def _grade_to_evidence_strength(content_grade: Optional[str]) -> str:
    """由 content_grade 派生 evidence_strength（title_only | full）。"""
    g = str(content_grade or "").strip().lower()
    return "full" if g == "full" else "title_only"


def _error_dict(message: str, **extra: Any) -> Dict[str, Any]:
    """构造工具/调用方可读的失败 dict（不抛 HTTP 500）。"""
    out: Dict[str, Any] = {"ok": False, "error": message}
    out.update(extra)
    return out


async def load_document_for_agent(
    doc_id: Union[int, str],
    company_id: Union[int, str],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> Dict[str, Any]:
    """
        按 doc_id + company_id 读取新闻正文（含 deleted 过滤）。

        SQL 四件套：id + company_id + deleted=b'0'。
        正文回退：content_text → content_summary → title；截断至 max_chars。

        Args:
            doc_id: radar_company_news_document.id
            company_id: 租户企业 ID
            max_chars: 返回 content 最大字符数

        Returns:
            成功含 content/truncated/content_grade/has_full_text/url/title/source_kind/
            evidence_strength；失败含 ok=False 与 error，永不抛未捕获异常。
    """
    did = str(doc_id).strip()
    cid = str(company_id).strip()
    if not did or not did.isdigit():
        return _error_dict("doc_id 无效", doc_id=did)
    if not cid or not str(cid).lstrip("-").isdigit():
        return _error_dict("company_id 无效", doc_id=did)

    limit = max(1, int(max_chars))
    sql = f"""
        SELECT id, company_id, title, url, content_text, content_summary,
               content_grade, source_kind, fetch_status
        FROM radar_company_news_document
        WHERE id = %s AND company_id = %s AND {_NOT_DELETED}
        LIMIT 1
    """
    try:
        if not settings.is_exhibition_mysql_enabled():
            return _error_dict(
                "exhibition MySQL 未配置，无法直读新闻正文",
                doc_id=did,
            )
        row = await run_db(query_one, sql, (int(did), int(cid)))
    except ExhibitionMysqlError as e:
        logger.warning("load_document_for_agent DB 配置/连接失败 doc_id=%s: %s", did, e)
        return _error_dict(f"数据库不可用: {e}", doc_id=did)
    except Exception as e:
        logger.warning("load_document_for_agent 查询异常 doc_id=%s: %s", did, e, exc_info=True)
        return _error_dict(f"读取文档失败: {e}", doc_id=did)

    if not row:
        return _error_dict("文档不存在或 company_id 不匹配", doc_id=did, company_id=cid)

    title = str(row.get("title") or "")
    raw_text = str(row.get("content_text") or "").strip()
    summary = str(row.get("content_summary") or "").strip()
    content_grade = str(row.get("content_grade") or "stub").strip().lower()
    if content_grade not in ("full", "stub"):
        content_grade = "full" if raw_text else "stub"

    if raw_text:
        body = raw_text
        has_full_text = True
    elif summary:
        body = summary
        has_full_text = False
    else:
        body = title
        has_full_text = False

    truncated = len(body) > limit
    content = body[:limit] if truncated else body

    return {
        "ok": True,
        "doc_id": did,
        "title": title,
        "url": str(row.get("url") or ""),
        "content": content,
        "truncated": truncated,
        "content_grade": content_grade,
        "has_full_text": has_full_text,
        "source_kind": row.get("source_kind"),
        "evidence_strength": _grade_to_evidence_strength(content_grade),
        "char_count": len(content),
    }
