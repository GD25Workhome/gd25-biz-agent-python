"""
科普文章 HTML 渲染路由

提供基于文章主键 ID 的独立 HTML 展示页面：
- 路径：/api/v1/articles/{id}
- 功能：从数据库查询 PopularScienceArticle 记录，将其中的 HTML 内容直接渲染到网页中
"""
import logging
import html
from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.connection import get_async_session
from backend.infrastructure.database.models.rag_models import PopularScienceArticle

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/articles/{article_id}",
    response_class=HTMLResponse,
    summary="根据ID渲染科普文章HTML页面",
)
async def render_popular_science_article(
    article_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    """
    根据主键 ID 查询科普文章并渲染为 HTML 页面。

    此接口直接返回完整的 HTML 文档，适合作为「引用文章详情页」在前端以超链接形式打开。

    Args:
        article_id: `PopularScienceArticle` 表中的主键 ID。
        session: 异步数据库会话（依赖注入）。

    Returns:
        HTMLResponse: 包含文章标题和正文内容的 HTML 页面。

    Raises:
        HTTPException:
            - 404: 当指定 ID 的文章不存在时抛出。
            - 500: 当查询或渲染过程中发生未预期错误时抛出。
    """
    try:
        # 使用主键 ID 查询文章记录
        article: PopularScienceArticle | None = await session.get(
            PopularScienceArticle,
            article_id,
        )

        if article is None:
            raise HTTPException(
                status_code=404,
                detail=f"科普文章不存在，id={article_id}",
            )

        # 标题使用 HTML 转义，避免被注入为 HTML
        safe_title: str = html.escape(article.article_title or "")

        # 正文内容本身即为 HTML 片段，这里按约定直接渲染
        # 如果未来需要增加安全过滤，可以在这里增加 HTML 清洗逻辑
        article_html: str = article.article_content or ""

        # 构造完整 HTML 文档
        full_html: str = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{safe_title}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif;
      margin: 0;
      padding: 0;
      background-color: #f5f5f5;
      color: #333;
      line-height: 1.6;
    }}
    .page-container {{
      max-width: 800px;
      margin: 0 auto;
      padding: 24px 16px 40px;
    }}
    .article-card {{
      background-color: #ffffff;
      border-radius: 12px;
      box-shadow: 0 6px 20px rgba(15, 23, 42, 0.08);
      padding: 24px;
    }}
    .article-title {{
      font-size: 1.5rem;
      font-weight: 700;
      margin: 0 0 16px;
      color: #111827;
    }}
    .article-meta {{
      font-size: 0.85rem;
      color: #6b7280;
      margin-bottom: 20px;
    }}
    .article-content {{
      font-size: 1rem;
      color: #111827;
    }}
    .article-content p {{
      margin: 0 0 1em;
    }}
    .article-content h1,
    .article-content h2,
    .article-content h3 {{
      margin-top: 1.4em;
      margin-bottom: 0.6em;
      font-weight: 600;
    }}
    .article-content ul,
    .article-content ol {{
      padding-left: 1.2em;
      margin-bottom: 1em;
    }}
    .article-content a {{
      color: #2563eb;
      text-decoration: none;
    }}
    .article-content a:hover {{
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <main class="page-container">
    <article class="article-card">
      <h1 class="article-title">{safe_title}</h1>
      <section class="article-content">
        {article_html}
      </section>
    </article>
  </main>
</body>
</html>"""

        return HTMLResponse(
            content=full_html,
            status_code=200,
        )
    except HTTPException:
        # 业务已知异常直接抛出给 FastAPI 处理
        raise
    except Exception as exc:  # pragma: no cover - 防御性兜底
        # 出现未预期异常时记录日志并返回 500
        await session.rollback()
        logger.error(
            "渲染科普文章HTML页面失败: id=%s, error=%s",
            article_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="渲染科普文章页面失败，请稍后重试。",
        )

