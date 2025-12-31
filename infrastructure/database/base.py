"""
SQLAlchemy Base 定义
"""
from ulid import ULID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def generate_ulid() -> str:
    """
    生成 ULID（Universally Unique Lexicographically Sortable Identifier）
    
    ULID 具有以下特性：
    - 26个字符（Base32编码）
    - 48位时间戳（毫秒） + 80位随机数
    - 按字典序排序即按时间排序
    - 全局唯一性
    
    Returns:
        str: ULID 字符串（26个字符）
    """
    return str(ULID())

