"""
知识库表查询，排除已在 embedding_records 中存在的记录。

设计文档：cursor_docs/012901-知识库Embedding导入脚本设计.md §3.2
"""
import logging
from typing import List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import settings
from backend.infrastructure.database.models.embedding_record import EmbeddingRecord
from backend.infrastructure.database.models.knowledge_base import KnowledgeBaseRecord

from scripts.embedding_import_qa.core.config import KNOWLEDGE_BASE_TABLE_NAME

logger = logging.getLogger(__name__)

_engine = None
_SessionFactory = None


def _ensure_psycopg3_sync_url(database_url: str) -> str:
    """确保数据库 URL 使用 psycopg3 驱动（同步模式）。"""
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if "+" in database_url and "://" in database_url:
        scheme, rest = database_url.split("://", 1)
        if scheme.startswith("postgresql+"):
            return f"postgresql+psycopg://{rest}"
    return database_url


def _get_engine():
    """懒加载引擎。"""
    global _engine
    if _engine is None:
        db_url = settings.DB_URI
        sync_url = _ensure_psycopg3_sync_url(db_url)
        _engine = create_engine(sync_url, echo=False)
        logger.debug("embedding_import_qa 数据库引擎已创建")
    return _engine


def get_db_session() -> Session:
    """返回同步 SQLAlchemy Session。"""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=_get_engine())
    return _SessionFactory()


def fetch_records_excluding_processed(
    limit: int,
    offset: int = 0,
) -> List[KnowledgeBaseRecord]:
    """
    查询未处理的知识库记录，排除已经在 embedding_records 表中存在的记录。

    匹配条件：
    - EmbeddingRecord.source_table_name = 知识库表名
    - EmbeddingRecord.source_record_id = KnowledgeBaseRecord.id

    Args:
        limit: 查询条数限制
        offset: 偏移量

    Returns:
        List[KnowledgeBaseRecord]: 未处理的记录列表，按 created_at 排序
    """
    session = get_db_session()
    try:
        q = (
            session.query(KnowledgeBaseRecord)
            .outerjoin(
                EmbeddingRecord,
                (EmbeddingRecord.source_table_name == KNOWLEDGE_BASE_TABLE_NAME)
                & (EmbeddingRecord.source_record_id == KnowledgeBaseRecord.id)
            )
            .filter(EmbeddingRecord.id.is_(None))
            .order_by(KnowledgeBaseRecord.created_at)
            .offset(offset)
            .limit(limit)
        )
        rows = q.all()
        logger.info(
            "查询未处理知识库记录: limit=%s, offset=%s, 结果数=%s",
            limit,
            offset,
            len(rows),
        )
        return list(rows)
    finally:
        session.close()
