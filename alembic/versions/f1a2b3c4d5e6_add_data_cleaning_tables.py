"""add data cleaning tables (pipeline_*)

Revision ID: f1a2b3c4d5e6
Revises: e4b533ea38cf
Create Date: 2025-02-04

设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
创建 pipeline_data_sets_path、pipeline_data_sets、pipeline_data_sets_items、pipeline_import_config 四张表。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e4b533ea38cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建数据清洗相关表。"""
    # 1. pipeline_data_sets_path
    op.create_table(
        "pipeline_data_sets_path",
        sa.Column("id", sa.String(length=50), nullable=False, comment="可主动设置，用于路径拼接"),
        sa.Column("id_path", sa.String(length=500), nullable=True, comment="上级路径"),
        sa.Column("name", sa.String(length=200), nullable=False, comment="名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="描述"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="扩展元数据"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pipeline_data_sets_path_id"), "pipeline_data_sets_path", ["id"], unique=False)
    op.create_index(op.f("ix_pipeline_data_sets_path_id_path"), "pipeline_data_sets_path", ["id_path"], unique=False)

    # 2. pipeline_data_sets
    op.create_table(
        "pipeline_data_sets",
        sa.Column("id", sa.String(length=50), nullable=False, comment="ULID 或业务 ID"),
        sa.Column("name", sa.String(length=200), nullable=False, comment="名称"),
        sa.Column("path_id", sa.String(length=50), nullable=True, comment="关联 dataSetsPath.id"),
        sa.Column("input_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="input 的 JSON Schema"),
        sa.Column("output_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="output 的 JSON Schema"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="扩展元数据"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["path_id"], ["pipeline_data_sets_path.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_pipeline_data_sets_id"), "pipeline_data_sets", ["id"], unique=False)
    op.create_index(op.f("ix_pipeline_data_sets_path_id_col"), "pipeline_data_sets", ["path_id"], unique=False)

    # 3. pipeline_data_sets_items
    op.create_table(
        "pipeline_data_sets_items",
        sa.Column("id", sa.String(length=50), nullable=False, comment="ULID"),
        sa.Column("dataset_id", sa.String(length=50), nullable=False, comment="关联 dataSets.id"),
        sa.Column("unique_key", sa.String(length=200), nullable=True, comment="业务唯一 key"),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="输入数据"),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="输出数据"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="扩展元数据"),
        sa.Column("status", sa.SmallInteger(), nullable=False, server_default=sa.text("1"), comment="1=激活，0=废弃"),
        sa.Column("source", sa.String(length=200), nullable=True, comment="来源"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["dataset_id"], ["pipeline_data_sets.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_pipeline_data_sets_items_id"), "pipeline_data_sets_items", ["id"], unique=False)
    op.create_index(op.f("ix_pipeline_data_sets_items_dataset_id"), "pipeline_data_sets_items", ["dataset_id"], unique=False)
    op.create_index(op.f("ix_pipeline_data_sets_items_unique_key"), "pipeline_data_sets_items", ["unique_key"], unique=False)

    # 4. pipeline_import_config
    op.create_table(
        "pipeline_import_config",
        sa.Column("id", sa.String(length=50), nullable=False, comment="ULID"),
        sa.Column("name", sa.String(length=200), nullable=False, comment="配置名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="描述"),
        sa.Column("import_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="导入逻辑配置"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pipeline_import_config_id"), "pipeline_import_config", ["id"], unique=False)


def downgrade() -> None:
    """删除数据清洗相关表。"""
    op.drop_index(op.f("ix_pipeline_import_config_id"), table_name="pipeline_import_config")
    op.drop_table("pipeline_import_config")

    op.drop_index(op.f("ix_pipeline_data_sets_items_unique_key"), table_name="pipeline_data_sets_items")
    op.drop_index(op.f("ix_pipeline_data_sets_items_dataset_id"), table_name="pipeline_data_sets_items")
    op.drop_index(op.f("ix_pipeline_data_sets_items_id"), table_name="pipeline_data_sets_items")
    op.drop_table("pipeline_data_sets_items")

    op.drop_index(op.f("ix_pipeline_data_sets_path_id_col"), table_name="pipeline_data_sets")
    op.drop_index(op.f("ix_pipeline_data_sets_id"), table_name="pipeline_data_sets")
    op.drop_table("pipeline_data_sets")

    op.drop_index(op.f("ix_pipeline_data_sets_path_id_path"), table_name="pipeline_data_sets_path")
    op.drop_index(op.f("ix_pipeline_data_sets_path_id"), table_name="pipeline_data_sets_path")
    op.drop_table("pipeline_data_sets_path")
