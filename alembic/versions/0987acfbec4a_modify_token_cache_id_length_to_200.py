"""modify_token_cache_id_length_to_200

Revision ID: 0987acfbec4a
Revises: 5187f9ead73b
Create Date: 2026-01-15 11:14:18.791284

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0987acfbec4a'
down_revision: Union[str, Sequence[str], None] = '5187f9ead73b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 修改token_cache表的id字段长度从50改为200
    op.alter_column(
        'gd2502_token_cache',
        'id',
        existing_type=sa.String(length=50),
        type_=sa.String(length=200),
        existing_nullable=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 回滚：将id字段长度从200改回50
    op.alter_column(
        'gd2502_token_cache',
        'id',
        existing_type=sa.String(length=200),
        type_=sa.String(length=50),
        existing_nullable=False
    )
