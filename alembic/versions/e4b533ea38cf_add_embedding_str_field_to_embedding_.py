"""add_embedding_str_field_to_embedding_records

Revision ID: e4b533ea38cf
Revises: b2c3d4e5f6a7
Create Date: 2026-01-29 09:59:40.244072

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e4b533ea38cf'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: 为 embedding_records 表新增 embedding_str 字段。"""
    op.add_column(
        'gd2502_embedding_records',
        sa.Column(
            'embedding_str',
            sa.Text(),
            nullable=True,
            comment='用于生成 embedding 的文本（scene_summary + optimization_question + ai_response 的格式化拼接）',
        ),
    )


def downgrade() -> None:
    """Downgrade schema: 移除 embedding_records 表的 embedding_str 字段。"""
    op.drop_column('gd2502_embedding_records', 'embedding_str')
