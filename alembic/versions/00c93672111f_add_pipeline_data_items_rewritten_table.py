"""add pipeline_data_items_rewritten table

Revision ID: 00c93672111f
Revises: f1a2b3c4d5e6
Create Date: 2026-02-06 11:12:49.846697

设计文档：doc/总体设计规划/数据归档-schema/Step2-数据初步筛选.md
创建 pipeline_data_items_rewritten 表，用于存储数据清洗第二阶段（改写与打标签）后的数据。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "00c93672111f"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 pipeline_data_items_rewritten 表。"""
    op.create_table(
        "pipeline_data_items_rewritten",
        sa.Column("id", sa.String(length=50), nullable=False, comment="ULID"),
        sa.Column("scenario_description", sa.Text(), nullable=True, comment="场景描述"),
        sa.Column("rewritten_question", sa.Text(), nullable=True, comment="改写后的问题"),
        sa.Column("rewritten_answer", sa.Text(), nullable=True, comment="改写后的回答"),
        sa.Column("rewritten_rule", sa.Text(), nullable=True, comment="改写后的规则"),
        sa.Column(
            "source_dataset_id",
            sa.String(length=100),
            nullable=True,
            comment="来源 dataSets.id",
        ),
        sa.Column(
            "source_item_id",
            sa.String(length=100),
            nullable=True,
            comment="来源 dataItems.id",
        ),
        sa.Column("scenario_type", sa.String(length=1000), nullable=True, comment="场景类型"),
        sa.Column(
            "sub_scenario_type",
            sa.String(length=1000),
            nullable=True,
            comment="子场景类型",
        ),
        sa.Column(
            "ai_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="AI 标签",
        ),
        sa.Column(
            "ai_score",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
            comment="AI 评分",
        ),
        sa.Column(
            "ai_score_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="AI 评分元数据",
        ),
        sa.Column(
            "manual_score",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
            comment="人工评分",
        ),
        sa.Column(
            "manual_score_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="人工评分元数据",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="创建时间（自动生成）",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="更新时间（自动更新）",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pipeline_data_items_rewritten_id"),
        "pipeline_data_items_rewritten",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pipeline_data_items_rewritten_source_dataset_id"),
        "pipeline_data_items_rewritten",
        ["source_dataset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pipeline_data_items_rewritten_source_item_id"),
        "pipeline_data_items_rewritten",
        ["source_item_id"],
        unique=False,
    )


def downgrade() -> None:
    """删除 pipeline_data_items_rewritten 表。"""
    op.drop_index(
        op.f("ix_pipeline_data_items_rewritten_source_item_id"),
        table_name="pipeline_data_items_rewritten",
    )
    op.drop_index(
        op.f("ix_pipeline_data_items_rewritten_source_dataset_id"),
        table_name="pipeline_data_items_rewritten",
    )
    op.drop_index(
        op.f("ix_pipeline_data_items_rewritten_id"),
        table_name="pipeline_data_items_rewritten",
    )
    op.drop_table("pipeline_data_items_rewritten")
