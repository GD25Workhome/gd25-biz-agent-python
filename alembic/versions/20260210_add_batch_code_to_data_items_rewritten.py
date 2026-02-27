"""add batch_code to pipeline_data_items_rewritten

Revision ID: a7f8e9d0c1b2
Revises: 94c68306053e
Create Date: 2026-02-10

为 pipeline_data_items_rewritten 表新增 batch_code 字段（批次code，String 100）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a7f8e9d0c1b2"
down_revision: Union[str, Sequence[str], None] = "94c68306053e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增 batch_code 字段。"""
    op.add_column(
        "pipeline_data_items_rewritten",
        sa.Column(
            "batch_code",
            sa.String(length=100),
            nullable=True,
            comment="批次code",
        ),
    )


def downgrade() -> None:
    """移除 batch_code 字段。"""
    op.drop_column("pipeline_data_items_rewritten", "batch_code")
