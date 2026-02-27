"""add job_type to batch_job

Revision ID: 20260227a001
Revises: 92b2c1042946
Create Date: 2026-02-27

设计文档：cursor_docs/022701-批次任务创建模版设计方案.md
在 batch_job 表增加 job_type 字段，供创建模版落库及运行阶段按类型路由执行器。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260227a001"
down_revision: Union[str, Sequence[str], None] = "92b2c1042946"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """batch_job 表增加 job_type 列。"""
    op.add_column(
        "batch_job",
        sa.Column(
            "job_type",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'unknown'"),
            comment="批次任务类型（如 embedding、data_clean 等）",
        ),
    )


def downgrade() -> None:
    """移除 batch_job.job_type。"""
    op.drop_column("batch_job", "job_type")
