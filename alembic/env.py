import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 将项目根目录添加到 sys.path，以便导入 app 和 infrastructure
sys.path.append(str(Path(__file__).resolve().parents[1]))

# 导入配置和模型
from app.core.config import settings
from infrastructure.database.base import Base
# 必须导入 models 以便 Base.metadata 能收集到表信息
from infrastructure.database import models  # noqa

# 这是 Alembic 的配置对象
config = context.config

# 解释配置文件以进行 Python 日志记录。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 覆盖 alembic.ini 中的 sqlalchemy.url
# 注意：alembic.ini 中通常是同步 driver (psycopg2)，但这里我们使用 async driver (asyncpg)
# 如果 alembic 内部需要同步 driver，可能需要转换，但 async_engine_from_config 应该能处理 async uri
config.set_main_option("sqlalchemy.url", settings.ASYNC_DB_URI)

# 在这里添加模型的 MetaData 对象
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """
    在 '离线' 模式下运行迁移。
    
    这将在不创建引擎的情况下配置上下文，仅需要一个 URL。
    默认情况下，调用 context.run_migrations() 会将生成的 SQL 输出到脚本输出。
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    """
    在 '在线' 模式下运行迁移。
    
    在这个场景中，我们需要创建一个引擎并将其与上下文关联。
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
