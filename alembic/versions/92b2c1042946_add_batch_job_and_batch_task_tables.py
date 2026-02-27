"""add batch_job and batch_task tables

Revision ID: 92b2c1042946
Revises: b8c9d0e1f2a3
Create Date: 2026-02-26

设计文档：cursor_docs/022603-数据embedding批次表字段设计.md
创建 batch_job、batch_task 表（数据 embedding 批次与子任务）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "92b2c1042946"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 batch_job、batch_task 表。"""
    op.create_table(
        "batch_job",
        sa.Column("id", sa.String(length=50), nullable=False, comment="ULID"),
        sa.Column("code", sa.String(length=64), nullable=False, comment="批次编码，唯一"),
        sa.Column("total_count", sa.Integer(), nullable=False, comment="本批次待 embedding 条数"),
        sa.Column("query_params", postgresql.JSON(astext_type=sa.Text()), nullable=True, comment="查询参数（如筛选条件、分页等）"),
        sa.Column("version", sa.Integer(), nullable=False, comment="版本号（自增，非乐观锁）"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="软删标记"),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=True, comment="更新时间（更新时由仓储赋值）"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batch_job_code"), "batch_job", ["code"], unique=True)
    op.create_index(op.f("ix_batch_job_id"), "batch_job", ["id"], unique=False)

    op.create_table(
        "batch_task",
        sa.Column("id", sa.String(length=50), nullable=False, comment="ULID"),
        sa.Column("job_id", sa.String(length=50), nullable=False, comment="关联批次表 batch_job.id"),
        sa.Column("source_table_id", sa.String(length=50), nullable=True, comment="来源表 ID（业务主键或来源系统 ID）"),
        sa.Column("source_table_name", sa.String(length=128), nullable=True, comment="来源表名（如 pipeline_data_items_rewritten）"),
        sa.Column("status", sa.String(length=32), nullable=True, comment="状态（如 pending/running/success/failed）"),
        sa.Column("runtime_params", postgresql.JSON(astext_type=sa.Text()), nullable=True, comment="运行时参数"),
        sa.Column("redundant_key", sa.String(length=256), nullable=True, comment="冗余 key（去重/幂等用）"),
        sa.Column("execution_result", sa.Text(), nullable=True, comment="执行返回结果"),
        sa.Column("execution_error_message", sa.Text(), nullable=True, comment="执行失败信息（含异常堆栈）"),
        sa.Column("execution_return_key", sa.String(length=256), nullable=True, comment="执行返回标识 key"),
        sa.Column("version", sa.Integer(), nullable=False, comment="版本号（自增，非乐观锁）"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="软删标记"),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=True, comment="更新时间（更新时由仓储赋值）"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batch_task_id"), "batch_task", ["id"], unique=False)
    op.create_index(op.f("ix_batch_task_job_id"), "batch_task", ["job_id"], unique=False)


def downgrade() -> None:
    """删除 batch_task、batch_job 表。"""
    op.drop_index(op.f("ix_batch_task_job_id"), table_name="batch_task")
    op.drop_index(op.f("ix_batch_task_id"), table_name="batch_task")
    op.drop_table("batch_task")
    op.drop_index(op.f("ix_batch_job_code"), table_name="batch_job")
    op.drop_index(op.f("ix_batch_job_id"), table_name="batch_job")
    op.drop_table("batch_job")
