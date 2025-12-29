"""add user_info field to users table

Revision ID: cc3c241433b0
Revises: b65f9b55f4e3
Create Date: 2025-01-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'cc3c241433b0'
down_revision: Union[str, None] = 'b65f9b55f4e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加 user_info 字段
    op.add_column('biz_agent_users', 
                  sa.Column('user_info', sa.Text(), nullable=True, comment='患者基础信息（多行文本）'))
    
    # 添加 user_info_updated_at 字段
    op.add_column('biz_agent_users',
                  sa.Column('user_info_updated_at', sa.DateTime(timezone=True), nullable=True, comment='患者基础信息更新时间'))


def downgrade() -> None:
    # 删除新增的字段
    op.drop_column('biz_agent_users', 'user_info_updated_at')
    op.drop_column('biz_agent_users', 'user_info')

