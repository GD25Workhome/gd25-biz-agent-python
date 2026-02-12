"""add pipeline_rewritten_batches table

Revision ID: b8c9d0e1f2a3
Revises: a7f8e9d0c1b2
Create Date: 2026-02-11

设计文档：cursor_docs/021101-Rewritten批次表与创建流程设计.md
创建 pipeline_rewritten_batches 表，集中管理 rewritten 批次的 batch_code 及元数据。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7f8e9d0c1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 pipeline_rewritten_batches 表。"""
    op.create_table(
        "pipeline_rewritten_batches",
        sa.Column("id", sa.String(length=50), nullable=False, comment="ULID"),
        sa.Column(
            "batch_code",
            sa.String(length=100),
            nullable=False,
            comment="批次编码",
        ),
        sa.Column(
            "total_count",
            sa.Integer(),
            nullable=False,
            comment="本批次数据项总量",
        ),
        sa.Column(
            "create_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="创建参数（JSON，含 dataset_id/dataset_ids 等）",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=True,
            comment="批次级状态（可选）",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pipeline_rewritten_batches_id"),
        "pipeline_rewritten_batches",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pipeline_rewritten_batches_batch_code"),
        "pipeline_rewritten_batches",
        ["batch_code"],
        unique=True,
    )


def downgrade() -> None:
    """删除 pipeline_rewritten_batches 表。"""
    op.drop_index(
        op.f("ix_pipeline_rewritten_batches_batch_code"),
        table_name="pipeline_rewritten_batches",
    )
    op.drop_index(
        op.f("ix_pipeline_rewritten_batches_id"),
        table_name="pipeline_rewritten_batches",
    )
    op.drop_table("pipeline_rewritten_batches")
