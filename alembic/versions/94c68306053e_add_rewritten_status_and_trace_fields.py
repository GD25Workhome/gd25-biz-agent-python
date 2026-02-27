"""add_rewritten_status_and_trace_fields

Revision ID: 94c68306053e
Revises: 00c93672111f
Create Date: 2026-02-09 13:34:05.671263

设计文档：cursor_docs/020901-insert_rewritten_data_func技术设计.md
为 pipeline_data_items_rewritten 表新增：
- rewrite_basis：改写依据
- scenario_confidence：场景置信度
- trace_id：流程 traceId
- status：执行状态
- execution_metadata：执行过程元数据
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '94c68306053e'
down_revision: Union[str, Sequence[str], None] = '00c93672111f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增改写后数据项表的状态与追踪字段。"""
    op.add_column(
        "pipeline_data_items_rewritten",
        sa.Column("rewrite_basis", sa.Text(), nullable=True, comment="改写依据"),
    )
    op.add_column(
        "pipeline_data_items_rewritten",
        sa.Column(
            "scenario_confidence",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
            comment="场景置信度（0-1）",
        ),
    )
    op.add_column(
        "pipeline_data_items_rewritten",
        sa.Column(
            "trace_id",
            sa.String(length=100),
            nullable=True,
            comment="流程执行 traceId",
        ),
    )
    op.add_column(
        "pipeline_data_items_rewritten",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=True,
            comment="执行状态：success / failed",
        ),
    )
    op.add_column(
        "pipeline_data_items_rewritten",
        sa.Column(
            "execution_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="执行过程元数据（失败原因及可扩展信息）",
        ),
    )
    op.create_index(
        op.f("ix_pipeline_data_items_rewritten_trace_id"),
        "pipeline_data_items_rewritten",
        ["trace_id"],
        unique=False,
    )


def downgrade() -> None:
    """移除新增的字段。"""
    op.drop_index(
        op.f("ix_pipeline_data_items_rewritten_trace_id"),
        table_name="pipeline_data_items_rewritten",
    )
    op.drop_column("pipeline_data_items_rewritten", "execution_metadata")
    op.drop_column("pipeline_data_items_rewritten", "status")
    op.drop_column("pipeline_data_items_rewritten", "trace_id")
    op.drop_column("pipeline_data_items_rewritten", "scenario_confidence")
    op.drop_column("pipeline_data_items_rewritten", "rewrite_basis")
