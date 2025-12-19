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


def normalize_postgres_uri(uri: str) -> str:
    """
    规范化 PostgreSQL 连接 URI
    
    将 SQLAlchemy 格式（postgresql+psycopg://）转换为标准 PostgreSQL URI 格式（postgresql://）
    psycopg_pool.AsyncConnectionPool 需要标准的 PostgreSQL URI 格式
    
    Args:
        uri: 原始连接 URI
        
    Returns:
        规范化后的连接 URI
    """
    # 将 postgresql+psycopg:// 或 postgresql+asyncpg:// 转换为 postgresql://
    if uri.startswith("postgresql+psycopg://"):
        return uri.replace("postgresql+psycopg://", "postgresql://", 1)
    elif uri.startswith("postgresql+asyncpg://"):
        return uri.replace("postgresql+asyncpg://", "postgresql://", 1)
    # 如果已经是标准格式，直接返回
    return uri


async def create_db_pool() -> AsyncConnectionPool:
    """
    创建业务数据库连接池
    
    Returns:
        AsyncConnectionPool: 数据库连接池
    """
    async def configure_connection(conn):
        """建立连接后设置数据库时区"""
        # 注意：在 autocommit=False 模式下，需要提交事务
        async with conn.cursor() as cur:
            await cur.execute(f"SET timezone = '{settings.DB_TIMEZONE}';")
            await conn.commit()
    
    # 规范化连接 URI，确保使用标准 PostgreSQL URI 格式
    db_uri = normalize_postgres_uri(settings.ASYNC_DB_URI)
    
    pool = AsyncConnectionPool(
        conninfo=db_uri,
        max_size=20,
        kwargs={"autocommit": False},
        configure=configure_connection
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
            max_overflow=20,
            connect_args={
                "options": f"-c timezone={settings.DB_TIMEZONE}"
            }
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

