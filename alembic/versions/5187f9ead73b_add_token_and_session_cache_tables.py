"""add_token_and_session_cache_tables

Revision ID: 5187f9ead73b
Revises: 29f1fe57ef5b
Create Date: 2026-01-15 11:11:19.985922

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5187f9ead73b'
down_revision: Union[str, Sequence[str], None] = '29f1fe57ef5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 创建token_cache表（极简设计：只有id和data_info两个字段）
    op.create_table(
        'gd2502_token_cache',
        sa.Column('id', sa.String(length=200), nullable=False, comment='Token ID（即user_id）'),
        sa.Column('data_info', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='UserInfo对象序列化数据'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建session_cache表（极简设计：只有id和data_info两个字段）
    op.create_table(
        'gd2502_session_cache',
        sa.Column('id', sa.String(length=200), nullable=False, comment='Session ID'),
        sa.Column('data_info', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Session上下文字典数据'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('gd2502_session_cache')
    op.drop_table('gd2502_token_cache')
