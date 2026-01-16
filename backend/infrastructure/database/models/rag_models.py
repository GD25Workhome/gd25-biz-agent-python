"""
RAG向量表模型
用于存储健康咨询问答、数据记录、数据查询、问候等示例的向量化数据
"""
from sqlalchemy import Column, String, Text, Integer, DateTime, ARRAY
from sqlalchemy.sql import func as sql_func

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    # 如果pgvector未安装，使用Text类型作为临时替代（不推荐用于生产）
    Vector = None
    HAS_PGVECTOR = False
    import warnings
    warnings.warn(
        "pgvector not installed. Vector columns will be defined as Text. "
        "Please install pgvector: pip install pgvector"
    )

from backend.infrastructure.database.base import Base, TABLE_PREFIX


class QAExample(Base):
    """健康咨询问答示例表"""
    
    __tablename__ = f"{TABLE_PREFIX}qa_examples"
    
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="主键ID"
    )
    user_input = Column(
        Text,
        nullable=False,
        comment="用户输入（问题）"
    )
    agent_response = Column(
        Text,
        nullable=False,
        comment="Agent回复（回答）"
    )
    tags = Column(
        ARRAY(String),
        nullable=True,
        comment="标签数组（可包含：问题类型、实体、场景类型等）"
    )
    quality_grade = Column(
        String(50),
        nullable=True,
        comment="质量等级（优秀/良好/一般）"
    )
    embedding = Column(
        Vector(768) if HAS_PGVECTOR else Text,  # 768维向量（使用moka-ai/m3e-base）
        nullable=True,  # 初始允许为空，数据导入时会填充
        comment="向量（768维，使用moka-ai/m3e-base）"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_func.now(),
        default=sql_func.now(),
        comment="创建时间（自动生成）"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=sql_func.now(),
        comment="更新时间（自动更新）"
    )
    
    def __repr__(self):
        return f"<QAExample(id={self.id}, user_input={self.user_input[:50]}...)>"


class RecordExample(Base):
    """数据记录示例表"""
    
    __tablename__ = f"{TABLE_PREFIX}record_examples"
    
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="主键ID"
    )
    user_input = Column(
        Text,
        nullable=False,
        comment="用户输入"
    )
    agent_response = Column(
        Text,
        nullable=False,
        comment="Agent回复"
    )
    tags = Column(
        ARRAY(String),
        nullable=True,
        comment="标签数组（可包含：记录类型、数据完整性等）"
    )
    quality_grade = Column(
        String(50),
        nullable=True,
        comment="质量等级（优秀/良好/一般）"
    )
    embedding = Column(
        Vector(768) if HAS_PGVECTOR else Text,  # 768维向量
        nullable=False,
        comment="向量（768维，使用moka-ai/m3e-base）"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_func.now(),
        default=sql_func.now(),
        comment="创建时间（自动生成）"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=sql_func.now(),
        comment="更新时间（自动更新）"
    )
    
    def __repr__(self):
        return f"<RecordExample(id={self.id}, user_input={self.user_input[:50]}...)>"


class QueryExample(Base):
    """数据查询示例表"""
    
    __tablename__ = f"{TABLE_PREFIX}query_examples"
    
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="主键ID"
    )
    user_input = Column(
        Text,
        nullable=False,
        comment="用户输入"
    )
    agent_response = Column(
        Text,
        nullable=False,
        comment="Agent回复"
    )
    tags = Column(
        ARRAY(String),
        nullable=True,
        comment="标签数组（可包含：查询类型、时间范围等）"
    )
    quality_grade = Column(
        String(50),
        nullable=True,
        comment="质量等级（优秀/良好/一般）"
    )
    embedding = Column(
        Vector(768) if HAS_PGVECTOR else Text,  # 768维向量
        nullable=False,
        comment="向量（768维，使用moka-ai/m3e-base）"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_func.now(),
        default=sql_func.now(),
        comment="创建时间（自动生成）"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=sql_func.now(),
        comment="更新时间（自动更新）"
    )
    
    def __repr__(self):
        return f"<QueryExample(id={self.id}, user_input={self.user_input[:50]}...)>"


class GreetingExample(Base):
    """问候示例表"""
    
    __tablename__ = f"{TABLE_PREFIX}greeting_examples"
    
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="主键ID"
    )
    user_input = Column(
        Text,
        nullable=False,
        comment="用户输入"
    )
    agent_response = Column(
        Text,
        nullable=False,
        comment="Agent回复"
    )
    tags = Column(
        ARRAY(String),
        nullable=True,
        comment="标签数组（可包含：问候类型等）"
    )
    quality_grade = Column(
        String(50),
        nullable=True,
        comment="质量等级（优秀/良好/一般）"
    )
    embedding = Column(
        Vector(768) if HAS_PGVECTOR else Text,  # 768维向量
        nullable=False,
        comment="向量（768维，使用moka-ai/m3e-base）"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_func.now(),
        default=sql_func.now(),
        comment="创建时间（自动生成）"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=sql_func.now(),
        comment="更新时间（自动更新）"
    )
    
    def __repr__(self):
        return f"<GreetingExample(id={self.id}, user_input={self.user_input[:50]}...)>"
