"""
Alembic 环境配置
"""
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# 导入应用配置和模型
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from infrastructure.database.base import Base
from infrastructure.database import models  # noqa: F401
from infrastructure.database.models import (
    User,
    BloodPressureRecord,
    Appointment,
    AppointmentStatus,
    LlmCallLog,
    LlmCallMessage,
    HealthEventRecord,
    MedicationRecord,
    SymptomRecord,
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# 设置数据库 URL
# 注意：保持 postgresql+psycopg:// 格式以使用 psycopg3 驱动
# 对于 Alembic 的同步操作，psycopg3 也支持同步模式
# 将异步 URL 转换为同步 URL（移除 async 相关参数，但保留驱动前缀）
sync_db_url = settings.ASYNC_DB_URI
# 确保使用 psycopg3 驱动（postgresql+psycopg://）
if sync_db_url.startswith("postgresql+psycopg://"):
    # 已经是正确的格式，直接使用
    pass
elif sync_db_url.startswith("postgresql://"):
    # 如果没有驱动前缀，添加 psycopg3 驱动
    sync_db_url = sync_db_url.replace("postgresql://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", sync_db_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

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


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # 使用 create_async_engine 创建异步引擎，确保使用 psycopg3
    # settings.ASYNC_DB_URI 已经是 postgresql+psycopg:// 格式
    connectable = create_async_engine(
        settings.ASYNC_DB_URI,
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

