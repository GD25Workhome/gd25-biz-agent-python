import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def reset_alembic_version():
    print(f"正在连接到 {settings.ASYNC_DB_URI}...")
    engine = create_async_engine(settings.ASYNC_DB_URI)
    async with engine.begin() as conn:
        print("如果存在 alembic_version 表，正在删除...")
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        print("完成。")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(reset_alembic_version())
