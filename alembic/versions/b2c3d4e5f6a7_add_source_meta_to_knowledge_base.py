"""add source_meta to knowledge_base

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-28

设计文档：cursor_docs/012804-QA场景独立记录转知识库脚本设计.md
在 knowledge_base 表中新增 source_meta（JSONB），用于存储来源信息（含 source_file 相对路径）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "gd2502_knowledge_base"


def upgrade() -> None:
    """在 knowledge_base 表中新增 source_meta 列（technical_tag_classification 之前）。"""
    op.add_column(
        TABLE_NAME,
        sa.Column(
            "source_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="来源信息（含 source_file 相对路径）",
        ),
    )


def downgrade() -> None:
    """移除 source_meta 列。"""
    op.drop_column(TABLE_NAME, "source_meta")
