"""
数据库连接和会话管理
"""
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.config import settings

# 全局变量
_async_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_async_engine() -> AsyncEngine:
    """
        获取异步数据库引擎（单例模式）。

        Returns:
            AsyncEngine: SQLAlchemy 异步引擎

        Raises:
            RuntimeError: 数据库未启用或未配置 DATABASE_URL
    """
    global _async_engine
    if _async_engine is None:
        # 无库模式下禁止隐式建连，尽早给出明确错误
        db_uri = settings.ASYNC_DB_URI
        _async_engine = create_async_engine(
            db_uri,
            echo=False,  # 生产环境建议关闭
            pool_pre_ping=True,  # 连接前检查连接是否有效
            pool_size=10,  # 连接池大小
            max_overflow=20,  # 最大溢出连接数
        )
    return _async_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
        获取异步会话工厂（单例模式）。

        Returns:
            async_sessionmaker: 异步会话工厂

        Raises:
            RuntimeError: 数据库未启用或未配置 DATABASE_URL
    """
    global _session_factory
    if _session_factory is None:
        engine = get_async_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
        获取异步数据库会话（依赖注入）。

        Yields:
            AsyncSession: 异步数据库会话

        Raises:
            RuntimeError: 数据库未启用或未配置 DATABASE_URL
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
