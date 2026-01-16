"""
向量库数据库连接模块
专门用于pgvector向量操作的同步连接（使用psycopg）

注意：
- 业务数据库操作使用异步连接（backend/infrastructure/database/connection.py）
- 向量库操作使用同步连接（本模块），因为pgvector的向量操作需要原生psycopg支持
"""
import logging
from typing import Optional
from urllib.parse import urlparse

import psycopg
from pgvector.psycopg import register_vector

from backend.app.config import settings

logger = logging.getLogger(__name__)


def parse_database_url(database_url: str) -> dict:
    """
    解析数据库连接URL，返回连接参数字典
    
    Args:
        database_url: 数据库连接URL，格式：postgresql+psycopg://user:password@host:port/dbname
        
    Returns:
        dict: 包含host, port, user, password, dbname的字典
    """
    # 移除驱动前缀（postgresql+psycopg:// -> postgresql://）
    url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    parsed = urlparse(url)
    
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname": parsed.path.lstrip("/") if parsed.path else "postgres"
    }


def get_vector_db_connection() -> psycopg.Connection:
    """
    获取向量库数据库连接（同步，用于pgvector操作）
    
    注意：
    - 使用psycopg同步连接，因为pgvector的向量操作（<=>操作符）需要原生支持
    - 业务数据库操作应使用异步连接（get_async_session）
    
    Returns:
        psycopg.Connection: 数据库连接对象（已注册vector类型）
    """
    database_url = settings.DATABASE_URL
    db_config = parse_database_url(database_url)
    
    # 构建连接字符串
    conn_string = (
        f"host={db_config['host']} "
        f"port={db_config['port']} "
        f"user={db_config['user']} "
        f"password={db_config['password']} "
        f"dbname={db_config['dbname']}"
    )
    
    conn = psycopg.connect(conn_string)
    
    # 注册vector类型（pgvector支持）
    register_vector(conn)
    
    return conn
