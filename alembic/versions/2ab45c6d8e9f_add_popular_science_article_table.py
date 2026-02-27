"""add_popular_science_article_table

Revision ID: 2ab45c6d8e9f
Revises: 613132195757
Create Date: 2026-01-16 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2ab45c6d8e9f'
down_revision: Union[str, Sequence[str], None] = '613132195757'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 确保pgvector扩展已安装（如果之前没有安装）
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    
    # 2. 创建科普文章表
    op.create_table('gd2502_popular_science_article',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键ID'),
    sa.Column('article_material_id', sa.String(length=100), nullable=False, comment='文章素材ID'),
    sa.Column('article_title', sa.Text(), nullable=False, comment='文章标题'),
    sa.Column('article_content', sa.Text(), nullable=False, comment='文章详情内容'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间（自动生成）'),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间（自动更新）'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('article_material_id')
    )
    op.create_index(op.f('ix_gd2502_popular_science_article_id'), 'gd2502_popular_science_article', ['id'], unique=False)
    op.create_index(op.f('ix_gd2502_popular_science_article_article_material_id'), 'gd2502_popular_science_article', ['article_material_id'], unique=True)
    
    # 添加embedding字段（使用SQL直接创建vector类型，基于文章标题的向量）
    op.execute("""
        ALTER TABLE gd2502_popular_science_article 
        ADD COLUMN embedding vector(768)
    """)
    op.execute("""
        COMMENT ON COLUMN gd2502_popular_science_article.embedding 
        IS '向量（768维，基于文章标题，使用moka-ai/m3e-base）'
    """)
    
    # 创建HNSW向量索引（用于向量检索）
    op.execute("""
        CREATE INDEX gd2502_popular_science_article_embedding_idx 
        ON gd2502_popular_science_article 
        USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # 删除索引和表
    op.execute("DROP INDEX IF EXISTS gd2502_popular_science_article_embedding_idx")
    op.drop_index(op.f('ix_gd2502_popular_science_article_article_material_id'), table_name='gd2502_popular_science_article')
    op.drop_index(op.f('ix_gd2502_popular_science_article_id'), table_name='gd2502_popular_science_article')
    op.drop_table('gd2502_popular_science_article')
    
    # 注意：不删除pgvector扩展，因为可能被其他表使用
