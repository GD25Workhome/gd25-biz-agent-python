"""add knowledge_base table

Revision ID: a1b2c3d4e5f6
Revises: d0e8b45e7586
Create Date: 2026-01-28

设计文档：cursor_docs/012803-知识库表与前端查询界面设计.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "d0e8b45e7586"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建知识库表 gd2502_knowledge_base。"""
    op.create_table(
        "gd2502_knowledge_base",
        sa.Column("id", sa.String(length=50), nullable=False, comment="记录ID（ULID）"),
        sa.Column("scene_summary", sa.Text(), nullable=True, comment="场景摘要"),
        sa.Column("optimization_question", sa.Text(), nullable=True, comment="优化问题"),
        sa.Column("reply_example_or_rule", sa.Text(), nullable=True, comment="回复示例或规则"),
        sa.Column("scene_category", sa.String(length=500), nullable=True, comment="场景分类"),
        sa.Column("input_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="输入标签数组"),
        sa.Column("response_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="回复标签数组"),
        sa.Column("raw_material_full_text", sa.Text(), nullable=True, comment="原始资料-全量文字"),
        sa.Column("raw_material_scene_summary", sa.Text(), nullable=True, comment="原始资料-场景简介"),
        sa.Column("raw_material_question", sa.Text(), nullable=True, comment="原始资料-提问"),
        sa.Column("raw_material_answer", sa.Text(), nullable=True, comment="原始资料-回答"),
        sa.Column("raw_material_other", sa.Text(), nullable=True, comment="原始资料-其它"),
        sa.Column("technical_tag_classification", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="技术标记分类"),
        sa.Column("business_tag_classification", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="业务标记分类"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间（自动生成）"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, comment="更新时间（自动更新）"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gd2502_knowledge_base_id"), "gd2502_knowledge_base", ["id"], unique=False)


def downgrade() -> None:
    """删除知识库表。"""
    op.drop_index(op.f("ix_gd2502_knowledge_base_id"), table_name="gd2502_knowledge_base")
    op.drop_table("gd2502_knowledge_base")
