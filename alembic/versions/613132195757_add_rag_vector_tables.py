"""add_rag_vector_tables

Revision ID: 613132195757
Revises: 1fb39c2bd34d
Create Date: 2026-01-16 14:13:55.361566

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '613132195757'
down_revision: Union[str, Sequence[str], None] = '1fb39c2bd34d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 确保pgvector扩展已安装（必须在表创建之前）
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    
    # 2. 创建QA示例表
    op.create_table('gd2502_qa_examples',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键ID'),
    sa.Column('user_input', sa.Text(), nullable=False, comment='用户输入（问题）'),
    sa.Column('agent_response', sa.Text(), nullable=False, comment='Agent回复（回答）'),
    sa.Column('tags', sa.ARRAY(sa.String()), nullable=True, comment='标签数组（可包含：问题类型、实体、场景类型等）'),
    sa.Column('quality_grade', sa.String(length=50), nullable=True, comment='质量等级（优秀/良好/一般）'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间（自动生成）'),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间（自动更新）'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gd2502_qa_examples_id'), 'gd2502_qa_examples', ['id'], unique=False)
    
    # 添加embedding字段（使用SQL直接创建vector类型，因为Alembic不支持直接创建Vector类型）
    # 先添加为可空字段，后续数据导入时会填充数据
    op.execute("""
        ALTER TABLE gd2502_qa_examples 
        ADD COLUMN embedding vector(768)
    """)
    op.execute("""
        COMMENT ON COLUMN gd2502_qa_examples.embedding 
        IS '向量（768维，使用moka-ai/m3e-base）'
    """)
    
    # 创建HNSW向量索引
    op.execute("""
        CREATE INDEX gd2502_qa_examples_embedding_idx 
        ON gd2502_qa_examples 
        USING hnsw (embedding vector_cosine_ops)
    """)
    
    # 3. 创建记录示例表
    op.create_table('gd2502_record_examples',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键ID'),
    sa.Column('user_input', sa.Text(), nullable=False, comment='用户输入'),
    sa.Column('agent_response', sa.Text(), nullable=False, comment='Agent回复'),
    sa.Column('tags', sa.ARRAY(sa.String()), nullable=True, comment='标签数组（可包含：记录类型、数据完整性等）'),
    sa.Column('quality_grade', sa.String(length=50), nullable=True, comment='质量等级（优秀/良好/一般）'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间（自动生成）'),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间（自动更新）'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gd2502_record_examples_id'), 'gd2502_record_examples', ['id'], unique=False)
    
    # 添加embedding字段
    op.execute("""
        ALTER TABLE gd2502_record_examples 
        ADD COLUMN embedding vector(768)
    """)
    op.execute("""
        COMMENT ON COLUMN gd2502_record_examples.embedding 
        IS '向量（768维，使用moka-ai/m3e-base）'
    """)
    
    # 创建HNSW向量索引
    op.execute("""
        CREATE INDEX gd2502_record_examples_embedding_idx 
        ON gd2502_record_examples 
        USING hnsw (embedding vector_cosine_ops)
    """)
    
    # 4. 创建查询示例表
    op.create_table('gd2502_query_examples',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键ID'),
    sa.Column('user_input', sa.Text(), nullable=False, comment='用户输入'),
    sa.Column('agent_response', sa.Text(), nullable=False, comment='Agent回复'),
    sa.Column('tags', sa.ARRAY(sa.String()), nullable=True, comment='标签数组（可包含：查询类型、时间范围等）'),
    sa.Column('quality_grade', sa.String(length=50), nullable=True, comment='质量等级（优秀/良好/一般）'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间（自动生成）'),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间（自动更新）'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gd2502_query_examples_id'), 'gd2502_query_examples', ['id'], unique=False)
    
    # 添加embedding字段
    op.execute("""
        ALTER TABLE gd2502_query_examples 
        ADD COLUMN embedding vector(768)
    """)
    op.execute("""
        COMMENT ON COLUMN gd2502_query_examples.embedding 
        IS '向量（768维，使用moka-ai/m3e-base）'
    """)
    
    # 创建HNSW向量索引
    op.execute("""
        CREATE INDEX gd2502_query_examples_embedding_idx 
        ON gd2502_query_examples 
        USING hnsw (embedding vector_cosine_ops)
    """)
    
    # 5. 创建问候示例表
    op.create_table('gd2502_greeting_examples',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键ID'),
    sa.Column('user_input', sa.Text(), nullable=False, comment='用户输入'),
    sa.Column('agent_response', sa.Text(), nullable=False, comment='Agent回复'),
    sa.Column('tags', sa.ARRAY(sa.String()), nullable=True, comment='标签数组（可包含：问候类型等）'),
    sa.Column('quality_grade', sa.String(length=50), nullable=True, comment='质量等级（优秀/良好/一般）'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间（自动生成）'),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间（自动更新）'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gd2502_greeting_examples_id'), 'gd2502_greeting_examples', ['id'], unique=False)
    
    # 添加embedding字段
    op.execute("""
        ALTER TABLE gd2502_greeting_examples 
        ADD COLUMN embedding vector(768)
    """)
    op.execute("""
        COMMENT ON COLUMN gd2502_greeting_examples.embedding 
        IS '向量（768维，使用moka-ai/m3e-base）'
    """)
    
    # 创建HNSW向量索引
    op.execute("""
        CREATE INDEX gd2502_greeting_examples_embedding_idx 
        ON gd2502_greeting_examples 
        USING hnsw (embedding vector_cosine_ops)
    """)
    
    # 6. 删除测试表（如果存在）
    try:
        op.drop_index(op.f('test_knowledge_base_embedding_idx'), table_name='test_knowledge_base', 
                     postgresql_ops={'embedding': 'vector_cosine_ops'}, postgresql_using='hnsw')
        op.drop_table('test_knowledge_base')
    except Exception:
        # 如果表不存在，忽略错误
        pass


def downgrade() -> None:
    """Downgrade schema."""
    # 删除表和索引（顺序与创建相反）
    
    # 删除问候示例表
    op.drop_index(op.f('ix_gd2502_greeting_examples_id'), table_name='gd2502_greeting_examples')
    op.execute("DROP INDEX IF EXISTS gd2502_greeting_examples_embedding_idx")
    op.drop_table('gd2502_greeting_examples')
    
    # 删除查询示例表
    op.drop_index(op.f('ix_gd2502_query_examples_id'), table_name='gd2502_query_examples')
    op.execute("DROP INDEX IF EXISTS gd2502_query_examples_embedding_idx")
    op.drop_table('gd2502_query_examples')
    
    # 删除记录示例表
    op.drop_index(op.f('ix_gd2502_record_examples_id'), table_name='gd2502_record_examples')
    op.execute("DROP INDEX IF EXISTS gd2502_record_examples_embedding_idx")
    op.drop_table('gd2502_record_examples')
    
    # 删除QA示例表
    op.drop_index(op.f('ix_gd2502_qa_examples_id'), table_name='gd2502_qa_examples')
    op.execute("DROP INDEX IF EXISTS gd2502_qa_examples_embedding_idx")
    op.drop_table('gd2502_qa_examples')
    
    # 注意：不删除pgvector扩展，因为可能被其他表使用
