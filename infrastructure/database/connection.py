"""
数据库连接和连接池管理
"""
from typing import Optional
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from infrastructure.database.base import Base


# 异步数据库引擎
_async_engine = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


async def create_db_pool() -> AsyncConnectionPool:
    """
    创建业务数据库连接池
    
    Returns:
        AsyncConnectionPool: 数据库连接池
    """
    pool = AsyncConnectionPool(
        conninfo=settings.ASYNC_DB_URI,
        max_size=20,
        kwargs={"autocommit": False}
    )
    await pool.open()
    return pool


def get_async_engine():
    """
    获取异步数据库引擎（单例模式）
    
    Returns:
        AsyncEngine: SQLAlchemy 异步引擎
    """
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            settings.ASYNC_DB_URI,
            echo=settings.DEBUG,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
    return _async_engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    获取异步会话工厂（单例模式）
    
    Returns:
        async_sessionmaker: 异步会话工厂
    """
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_async_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    return _async_session_factory


async def get_async_session() -> AsyncSession:
    """
    获取异步数据库会话
    
    Returns:
        AsyncSession: 异步数据库会话
    """
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        yield session


async def init_db():
    """
    初始化数据库（创建表）
    """
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

