"""
知识库模型
用于存储 RAG/向量话术场景下的场景摘要、优化问题、回复示例与规则、场景分类及各类标签。
设计文档：cursor_docs/012803-知识库表与前端查询界面设计.md
"""
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, TABLE_PREFIX, generate_ulid


class KnowledgeBaseRecord(Base):
    """知识库记录模型"""

    __tablename__ = f"{TABLE_PREFIX}knowledge_base"

    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="记录ID（ULID）",
    )
    scene_summary = Column(
        Text,
        nullable=True,
        comment="场景摘要（对应 create_rag_agent 输出 scene_summary）",
    )
    optimization_question = Column(
        Text,
        nullable=True,
        comment="优化问题，可为单字符串或数组的序列化存储",
    )
    reply_example_or_rule = Column(
        Text,
        nullable=True,
        comment="回复示例或规则",
    )
    scene_category = Column(
        String(500),
        nullable=True,
        comment="场景分类",
    )
    input_tags = Column(
        JSONB,
        nullable=True,
        comment="输入标签数组 [\"tag1\",\"tag2\",...]",
    )
    response_tags = Column(
        JSONB,
        nullable=True,
        comment="回复标签数组 [\"tag1\",\"tag2\",...]",
    )
    raw_material_full_text = Column(
        Text,
        nullable=True,
        comment="原始资料-全量文字",
    )
    raw_material_scene_summary = Column(
        Text,
        nullable=True,
        comment="原始资料-场景简介",
    )
    raw_material_question = Column(
        Text,
        nullable=True,
        comment="原始资料-提问",
    )
    raw_material_answer = Column(
        Text,
        nullable=True,
        comment="原始资料-回答",
    )
    raw_material_other = Column(
        Text,
        nullable=True,
        comment="原始资料-其它",
    )
    source_meta = Column(
        JSONB,
        nullable=True,
        comment="来源信息（含 source_file 相对路径）",
    )
    technical_tag_classification = Column(
        JSONB,
        nullable=True,
        comment="技术标记分类（JSON）",
    )
    business_tag_classification = Column(
        JSONB,
        nullable=True,
        comment="业务标记分类（JSON）",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_func.now(),
        default=sql_func.now(),
        comment="创建时间（自动生成）",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=sql_func.now(),
        comment="更新时间（自动更新）",
    )

    def __repr__(self):
        return f"<KnowledgeBaseRecord(id={self.id}, scene_category={self.scene_category})>"
