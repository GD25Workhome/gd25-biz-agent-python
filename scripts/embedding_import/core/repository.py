"""
数据库查询

从 blood_pressure_session_records 表读取记录，复用 import_blood_pressure_session_data 的
引擎 / sessionmaker、ensure_psycopg3_sync_url。见设计文档 §8.6。
"""
import logging
from typing import List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import settings
from backend.infrastructure.database.models.blood_pressure_session import (
    BloodPressureSessionRecord,
)
from backend.infrastructure.database.models.embedding_record import EmbeddingRecord

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
        logger.debug("embedding_import 数据库引擎已创建")
    return _engine


def get_db_session() -> Session:
    """返回同步 SQLAlchemy Session，供 fetch_records 使用。"""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=_get_engine())
    return _SessionFactory()


def fetch_records(
    limit: int,
    offset: int = 0,
) -> List[BloodPressureSessionRecord]:
    """
    查询表，ORDER BY created_at，LIMIT limit OFFSET offset。
    """
    session = get_db_session()
    try:
        q = (
            session.query(BloodPressureSessionRecord)
            .order_by(BloodPressureSessionRecord.created_at)
            .offset(offset)
            .limit(limit)
        )
        rows = q.all()
        return list(rows)
    finally:
        session.close()


def fetch_records_excluding_processed(
    limit: int,
    offset: int = 0,
) -> List[BloodPressureSessionRecord]:
    """
    查询未处理的记录，排除已经在 embedding_record 表中存在的记录。
    
    匹配条件：
    - embedding_record.source_table_name = 'blood_pressure_session_records'
    - embedding_record.source_record_id = blood_pressure_session_records.id
    
    Args:
        limit: 查询条数限制
        offset: 偏移量
        
    Returns:
        List[BloodPressureSessionRecord]: 未处理的记录列表，按 created_at 排序
    """
    session = get_db_session()
    try:
        # 使用 LEFT JOIN + IS NULL 来排除已存在的记录
        # 匹配条件：source_table_name = 'blood_pressure_session_records' 
        # 且 source_record_id = BloodPressureSessionRecord.id
        q = (
            session.query(BloodPressureSessionRecord)
            .outerjoin(
                EmbeddingRecord,
                (EmbeddingRecord.source_table_name == "blood_pressure_session_records")
                & (EmbeddingRecord.source_record_id == BloodPressureSessionRecord.id)
            )
            .filter(EmbeddingRecord.id.is_(None))  # 排除已存在的记录
            .order_by(BloodPressureSessionRecord.created_at)
            .offset(offset)
            .limit(limit)
        )
        rows = q.all()
        logger.info(
            f"查询未处理记录: limit={limit}, offset={offset}, 结果数={len(rows)}"
        )
        return list(rows)
    finally:
        session.close()
