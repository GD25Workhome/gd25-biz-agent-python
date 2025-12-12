from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

engine = create_async_engine(
    settings.ASYNC_DB_URI,
    echo=settings.LOG_LEVEL == "DEBUG",
    future=True,
    pool_pre_ping=True
)

# 创建异步 Session 工厂
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def get_db() -> AsyncSession:
    """
    获取数据库会话 (Dependency Injection)。
    
    用于 FastAPI 的 Depends() 或手动上下文管理。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
