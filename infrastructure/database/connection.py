"""
数据库连接和连接池管理
"""
import time
import logging
from typing import Optional
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event

from app.core.config import settings
from infrastructure.database.base import Base

# SQL日志记录器
sql_logger = logging.getLogger("infrastructure.database.connection")


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


def setup_db_logging(engine):
    """
    设置数据库SQL日志监听器
    
    通过SQLAlchemy事件系统监听SQL执行，记录SQL语句、参数、执行时间等信息
    
    Args:
        engine: SQLAlchemy引擎实例
    """
    if not settings.DB_SQL_LOG_ENABLED:
        return
    
    # 设置日志级别
    log_level = getattr(logging, settings.DB_SQL_LOG_LEVEL.upper(), logging.INFO)
    sql_logger.setLevel(log_level)
    
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """
        SQL执行前事件监听器
        
        记录SQL语句和参数，记录执行开始时间
        """
        # 记录执行开始时间（使用栈结构支持嵌套查询）
        conn.info.setdefault('query_start_time', []).append(time.time())
        
        # 只在DEBUG级别记录详细SQL信息
        if sql_logger.isEnabledFor(logging.DEBUG):
            # 处理SQL语句：移除多余空白，不限制长度
            sql = statement.strip()
            
            # 处理参数：根据配置决定是否记录
            log_params = None
            if settings.DB_SQL_LOG_INCLUDE_PARAMS:
                # 将参数转换为可记录的格式
                if parameters:
                    if isinstance(parameters, (list, tuple)):
                        # 限制参数数量，避免日志过大
                        log_params = list(parameters[:10])  # 最多记录10个参数
                        if len(parameters) > 10:
                            log_params.append(f"... (还有 {len(parameters) - 10} 个参数)")
                    else:
                        log_params = str(parameters)[:500]  # 限制参数字符串长度
            
            # 注意：不进行参数替换，保持SQL和参数分离，确保安全性
            sql_logger.debug(
                "Executing SQL",
                extra={
                    "event": "before_cursor_execute",
                    "sql": sql,  # 原始SQL（带占位符）
                    "parameters": log_params,  # 参数（不进行字符串替换）
                    "executemany": executemany
                }
            )
    
    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """
        SQL执行后事件监听器
        
        计算执行时间，记录执行结果摘要，检测慢查询
        """
        # 获取执行开始时间
        if 'query_start_time' in conn.info and conn.info['query_start_time']:
            start_time = conn.info['query_start_time'].pop(-1)
            duration = time.time() - start_time
            duration_ms = duration * 1000
            
            # 处理SQL语句：移除多余空白，不限制长度
            sql = statement.strip()
            
            # 检测慢查询
            is_slow_query = duration_ms > (settings.DB_SQL_LOG_SLOW_QUERY_THRESHOLD * 1000)
            
            # 处理参数：根据配置决定是否记录
            log_params = None
            if settings.DB_SQL_LOG_INCLUDE_PARAMS:
                if parameters:
                    if isinstance(parameters, (list, tuple)):
                        # 限制参数数量，避免日志过大
                        log_params = list(parameters[:10])  # 最多记录10个参数
                        if len(parameters) > 10:
                            log_params.append(f"... (还有 {len(parameters) - 10} 个参数)")
                    else:
                        log_params = str(parameters)[:500]  # 限制参数字符串长度
            
            # 构建日志额外信息
            # 注意：不进行参数替换，保持SQL和参数分离，确保安全性
            # 如需查看实际执行的SQL，请使用PostgreSQL服务器日志（log_statement=all）
            extra = {
                "event": "after_cursor_execute",
                "sql": sql,  # 原始SQL（带占位符）
                "parameters": log_params,  # 参数（根据配置决定是否记录），不进行字符串替换
                "duration_ms": round(duration_ms, 2),
                "is_slow_query": is_slow_query,
                "executemany": executemany
            }
            
            # 如果是慢查询，添加阈值信息
            if is_slow_query:
                extra["threshold_ms"] = settings.DB_SQL_LOG_SLOW_QUERY_THRESHOLD * 1000
            
            # 根据是否为慢查询选择日志级别
            if is_slow_query:
                sql_logger.warning(
                    "Slow SQL query detected",
                    extra=extra
                )
            else:
                sql_logger.info(
                    "SQL executed successfully",
                    extra=extra
                )
    
    @event.listens_for(engine.sync_engine, "handle_error")
    def receive_handle_error(exception_context):
        """
        SQL执行错误事件监听器
        
        记录错误信息、SQL语句和参数
        """
        # 处理SQL语句：移除多余空白，不限制长度
        sql = ""
        if exception_context.statement:
            sql = exception_context.statement.strip()
        
        # 处理参数
        log_params = None
        if settings.DB_SQL_LOG_INCLUDE_PARAMS and exception_context.parameters:
            if isinstance(exception_context.parameters, (list, tuple)):
                log_params = list(exception_context.parameters[:10])
                if len(exception_context.parameters) > 10:
                    log_params.append(f"... (还有 {len(exception_context.parameters) - 10} 个参数)")
            else:
                log_params = str(exception_context.parameters)[:500]
        
        # 获取错误信息
        error = str(exception_context.original_exception)
        error_type = type(exception_context.original_exception).__name__
        
        sql_logger.error(
            "SQL execution error",
            extra={
                "event": "handle_error",
                "sql": sql,
                "parameters": log_params,
                "error": error,
                "error_type": error_type
            },
            exc_info=exception_context.original_exception
        )


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
        # 设置SQL日志监听器
        setup_db_logging(_async_engine)
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
            expire_on_commit=False,
            # 在 SQLAlchemy 2.0+ 中，async_sessionmaker 使用 async with 时，
            # 如果没有异常会自动提交，如果有异常会自动回滚
            # 如果手动调用了 commit()，需要确保不会在退出时再次回滚
            # 通过设置 autocommit=False，确保事务由我们手动管理
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

