"""add pipeline_embedding_records table

Revision ID: 20260228a001
Revises: 20260227a001
Create Date: 2026-02-28

设计文档：cursor_docs/022801-pipeline_embedding_records表与model-repository技术设计.md
创建 pipeline_embedding_records 表（Step3 Embedding 记录，带审计字段）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

try:
    import pgvector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False

revision: str = "20260228a001"
down_revision: Union[str, Sequence[str], None] = "20260227a001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "pipeline_embedding_records"


def upgrade() -> None:
    """创建 pipeline_embedding_records 表（前缀 pipeline_，业务名 embedding_records）。"""
    columns = [
        sa.Column("id", sa.String(length=50), nullable=False, comment="ULID"),
        sa.Column("embedding_str", sa.Text(), nullable=True, comment="用于生成 embedding 的文本"),
        sa.Column(
            "embedding_type",
            sa.String(length=50),
            nullable=True,
            comment="类型：Q（仅提问）、QA（提问+回答）",
        ),
        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="是否发布",
        ),
        sa.Column("type", sa.String(length=64), nullable=True, comment="主分类"),
        sa.Column("sub_type", sa.String(length=64), nullable=True, comment="子分类（业务上若为空可用主分类填充）"),
        sa.Column("metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True, comment="扩展元数据"),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="版本号（自增，非乐观锁）",
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="软删标记",
        ),
        sa.Column(
            "create_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "update_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="更新时间（更新时由仓储赋值）",
        ),
    ]
    if HAS_PGVECTOR:
        columns.insert(
            2,
            sa.Column(
                "embedding_value",
                pgvector.sqlalchemy.vector.VECTOR(dim=2048),
                nullable=True,
                comment="Embedding 向量值（2048 维）",
            ),
        )
    else:
        columns.insert(
            2,
            sa.Column(
                "embedding_value",
                sa.Text(),
                nullable=True,
                comment="Embedding 向量值（2048 维）",
            ),
        )
    op.create_table(
        TABLE_NAME,
        *columns,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f(f"ix_{TABLE_NAME}_id"),
        TABLE_NAME,
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    """删除 pipeline_embedding_records 表。"""
    op.drop_index(op.f(f"ix_{TABLE_NAME}_id"), table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
