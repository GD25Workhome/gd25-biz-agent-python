"""
改写后数据项模型
用于存储数据清洗第二阶段（改写与打标签）后的数据。
上游来源于 pipeline_data_sets_items，经 Agent 改写后提取字段存入本表。
设计文档：doc/总体设计规划/数据归档-schema/Step2-数据初步筛选.md
"""
from sqlalchemy import Column, String, Text, DateTime, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, generate_ulid


PIPELINE_TABLE_PREFIX = "pipeline_"


class DataItemsRewrittenRecord(Base):
    """改写后数据项"""

    __tablename__ = f"{PIPELINE_TABLE_PREFIX}data_items_rewritten"

    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="ULID",
    )
    scenario_description = Column(
        Text,
        nullable=True,
        comment="场景描述",
    )
    rewritten_question = Column(
        Text,
        nullable=True,
        comment="改写后的问题",
    )
    rewritten_answer = Column(
        Text,
        nullable=True,
        comment="改写后的回答",
    )
    rewritten_rule = Column(
        Text,
        nullable=True,
        comment="改写后的规则",
    )
    source_dataset_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="来源 dataSets.id",
    )
    source_item_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="来源 dataItems.id",
    )
    scenario_type = Column(
        String(1000),
        nullable=True,
        comment="场景类型",
    )
    sub_scenario_type = Column(
        String(1000),
        nullable=True,
        comment="子场景类型",
    )
    rewrite_basis = Column(
        Text,
        nullable=True,
        comment="改写依据",
    )
    scenario_confidence = Column(
        Numeric(10, 4),
        nullable=True,
        comment="场景置信度（0-1）",
    )
    trace_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="流程执行 traceId",
    )
    batch_code = Column(
        String(100),
        nullable=True,
        comment="批次code",
    )
    status = Column(
        String(20),
        nullable=True,
        comment="执行状态：init / processing / success / failed",
    )
    execution_metadata = Column(
        JSONB,
        nullable=True,
        comment="执行过程元数据（失败原因及可扩展信息）",
    )
    ai_tags = Column(
        JSONB,
        nullable=True,
        comment="AI 标签",
    )
    ai_score = Column(
        Numeric(10, 4),
        nullable=True,
        comment="AI 评分",
    )
    ai_score_metadata = Column(
        JSONB,
        nullable=True,
        comment="AI 评分元数据",
    )
    manual_score = Column(
        Numeric(10, 4),
        nullable=True,
        comment="人工评分",
    )
    manual_score_metadata = Column(
        JSONB,
        nullable=True,
        comment="人工评分元数据",
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

    def __repr__(self) -> str:
        return f"<DataItemsRewrittenRecord(id={self.id}, source_item_id={self.source_item_id})>"
