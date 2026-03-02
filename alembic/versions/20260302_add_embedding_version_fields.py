"""add pipeline_embedding_records version and trace fields

Revision ID: 20260302a001
Revises: 20260228a001
Create Date: 2026-03-02

设计文档：cursor_docs/030206-pipeline_embedding_record版本与溯源技术设计.md
为 pipeline_embedding_records 表新增版本控制三列：data_version、snapshot_id、business_key。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260302a001"
down_revision: Union[str, Sequence[str], None] = "20260228a001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "pipeline_embedding_records"


def upgrade() -> None:
    """新增 data_version、snapshot_id、business_key 三列及索引。"""
    op.add_column(
        TABLE_NAME,
        sa.Column(
            "data_version",
            sa.Integer(),
            nullable=True,
            comment="同一 business_key 下数据版本号",
        ),
    )
    op.add_column(
        TABLE_NAME,
        sa.Column(
            "snapshot_id",
            sa.String(length=50),
            nullable=True,
            comment="某次全量快照/发布批次 ID",
        ),
    )
    op.add_column(
        TABLE_NAME,
        sa.Column(
            "business_key",
            sa.String(length=256),
            nullable=True,
            comment="业务唯一键，识别同一条逻辑数据",
        ),
    )
    op.create_index(
        op.f(f"ix_{TABLE_NAME}_snapshot_id"),
        TABLE_NAME,
        ["snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f(f"ix_{TABLE_NAME}_business_key"),
        TABLE_NAME,
        ["business_key"],
        unique=False,
    )


def downgrade() -> None:
    """删除三列及索引。"""
    op.drop_index(op.f(f"ix_{TABLE_NAME}_business_key"), table_name=TABLE_NAME)
    op.drop_index(op.f(f"ix_{TABLE_NAME}_snapshot_id"), table_name=TABLE_NAME)
    op.drop_column(TABLE_NAME, "business_key")
    op.drop_column(TABLE_NAME, "snapshot_id")
    op.drop_column(TABLE_NAME, "data_version")
