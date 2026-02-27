"""
Embedding 记录模型
用于存储词干提取后的结构化数据
"""
import json
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
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

from backend.infrastructure.database.base import Base, TABLE_PREFIX, generate_ulid


class EmbeddingRecord(Base):
    """Embedding 记录模型"""
    
    __tablename__ = f"{TABLE_PREFIX}embedding_records"
    
    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="记录ID（ULID）"
    )
    scene_summary = Column(
        Text,
        nullable=False,
        comment="场景摘要"
    )
    optimization_question = Column(
        Text,
        nullable=False,
        comment="优化后的问题"
    )
    input_tags = Column(
        Text,
        nullable=True,
        comment="输入标签（JSON数组字符串）"
    )
    response_tags = Column(
        Text,
        nullable=True,
        comment="响应标签（JSON数组字符串）"
    )
    ai_response = Column(
        Text,
        nullable=True,
        comment="AI回复内容（来自原始表的new_session_response）"
    )
    embedding_str = Column(
        Text,
        nullable=True,
        comment="用于生成 embedding 的文本（scene_summary + optimization_question + ai_response 的格式化拼接）"
    )
    embedding_value = Column(
        Vector(2048) if HAS_PGVECTOR else Text,
        nullable=True,
        comment="Embedding向量值（2048维，由embedding_node生成）"
    )
    message_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="消息ID（关联数据源）"
    )
    trace_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="Trace ID（用于可观测性追踪，关联 Langfuse）"
    )
    version = Column(
        Integer,
        nullable=False,
        default=0,
        comment="版本号（从0开始递增）"
    )
    is_published = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否发布"
    )
    source_table_name = Column(
        String(200),
        nullable=True,
        comment="数据来源表名"
    )
    source_record_id = Column(
        String(50),
        nullable=True,
        comment="数据来源记录ID"
    )
    generation_status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="生成状态（0=进行中，1=成功，-1=失败）"
    )
    failure_reason = Column(
        Text,
        nullable=True,
        comment="失败原因（包含异常堆栈信息）"
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
        return (
            f"<EmbeddingRecord(id={self.id}, "
            f"message_id={self.message_id}, "
            f"trace_id={self.trace_id}, "
            f"version={self.version}, "
            f"generation_status={self.generation_status})>"
        )
    
    def get_input_tags_list(self) -> list:
        """
        获取 input_tags 的列表形式
        
        Returns:
            list: 输入标签列表
        """
        if not self.input_tags:
            return []
        try:
            return json.loads(self.input_tags)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def get_response_tags_list(self) -> list:
        """
        获取 response_tags 的列表形式
        
        Returns:
            list: 响应标签列表
        """
        if not self.response_tags:
            return []
        try:
            return json.loads(self.response_tags)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_input_tags_list(self, tags: list) -> None:
        """
        设置 input_tags（从列表转换为 JSON 字符串）
        
        Args:
            tags: 输入标签列表
        """
        if tags:
            self.input_tags = json.dumps(tags, ensure_ascii=False)
        else:
            self.input_tags = None
    
    def set_response_tags_list(self, tags: list) -> None:
        """
        设置 response_tags（从列表转换为 JSON 字符串）
        
        Args:
            tags: 响应标签列表
        """
        if tags:
            self.response_tags = json.dumps(tags, ensure_ascii=False)
        else:
            self.response_tags = None
