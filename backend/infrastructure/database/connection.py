"""
数据库连接和会话管理
"""
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from typing import AsyncGenerator, Optional

from backend.app.config import settings

# 全局变量
_async_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_async_engine() -> AsyncEngine:
    """
    获取异步数据库引擎（单例模式）
    
    Returns:
        AsyncEngine: SQLAlchemy 异步引擎
    """
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            settings.ASYNC_DB_URI,
            echo=False,  # 生产环境建议关闭
            pool_pre_ping=True,  # 连接前检查连接是否有效
            pool_size=10,  # 连接池大小
            max_overflow=20,  # 最大溢出连接数
        )
    return _async_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    获取异步会话工厂（单例模式）
    
    Returns:
        async_sessionmaker: 异步会话工厂
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
    获取异步数据库会话（依赖注入）
    
    Yields:
        AsyncSession: 异步数据库会话
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session

