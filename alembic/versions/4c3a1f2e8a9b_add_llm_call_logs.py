"""add llm call logs tables

Revision ID: 4c3a1f2e8a9b
Revises: f297d7a76db3
Create Date: 2025-12-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c3a1f2e8a9b'
down_revision: Union[str, None] = 'f297d7a76db3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增 LLM 调用日志相关表"""
    op.create_table(
        'biz_agent_llm_call_logs',
        sa.Column('id', sa.Integer(), nullable=False, comment='主键ID'),
        sa.Column('call_id', sa.String(length=64), nullable=False, comment='调用唯一ID'),
        sa.Column('trace_id', sa.String(length=64), nullable=True, comment='链路追踪ID'),
        sa.Column('session_id', sa.String(length=64), nullable=True, comment='会话ID'),
        sa.Column('conversation_id', sa.String(length=64), nullable=True, comment='对话ID'),
        sa.Column('user_id', sa.Integer(), nullable=True, comment='用户ID'),
        sa.Column('agent_key', sa.String(length=100), nullable=True, comment='智能体标识'),
        sa.Column('model', sa.String(length=100), nullable=False, comment='模型名称'),
        sa.Column('temperature', sa.Numeric(4, 2), nullable=True, comment='温度参数'),
        sa.Column('top_p', sa.Numeric(4, 2), nullable=True, comment='Top-p 参数'),
        sa.Column('max_tokens', sa.Integer(), nullable=True, comment='最大输出 tokens'),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True, comment='提示 tokens 消耗'),
        sa.Column('completion_tokens', sa.Integer(), nullable=True, comment='生成 tokens 消耗'),
        sa.Column('total_tokens', sa.Integer(), nullable=True, comment='总 tokens 消耗'),
        sa.Column('latency_ms', sa.Integer(), nullable=True, comment='耗时（毫秒）'),
        sa.Column('success', sa.Boolean(), nullable=True, comment='是否成功'),
        sa.Column('error_code', sa.String(length=50), nullable=True, comment='错误码'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
        sa.Column('prompt_snapshot', sa.Text(), nullable=True, comment='提示词快照'),
        sa.Column('response_snapshot', sa.Text(), nullable=True, comment='响应快照'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column('finished_at', sa.DateTime(), nullable=True, comment='完成时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('call_id')
    )
    op.create_index(op.f('ix_biz_agent_llm_call_logs_agent_key'), 'biz_agent_llm_call_logs', ['agent_key'], unique=False)
    op.create_index(op.f('ix_biz_agent_llm_call_logs_call_id'), 'biz_agent_llm_call_logs', ['call_id'], unique=True)
    op.create_index(op.f('ix_biz_agent_llm_call_logs_session_id'), 'biz_agent_llm_call_logs', ['session_id'], unique=False)
    op.create_index(op.f('ix_biz_agent_llm_call_logs_trace_id'), 'biz_agent_llm_call_logs', ['trace_id'], unique=False)
    op.create_index(op.f('ix_biz_agent_llm_call_logs_user_id'), 'biz_agent_llm_call_logs', ['user_id'], unique=False)
    
    op.create_table(
        'biz_agent_llm_call_messages',
        sa.Column('id', sa.Integer(), nullable=False, comment='主键ID'),
        sa.Column('call_id', sa.String(length=64), nullable=False, comment='调用唯一ID'),
        sa.Column('role', sa.String(length=20), nullable=False, comment='消息角色'),
        sa.Column('content', sa.Text(), nullable=False, comment='消息内容'),
        sa.Column('token_estimate', sa.Integer(), nullable=True, comment='token 粗略估算'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.ForeignKeyConstraint(['call_id'], ['biz_agent_llm_call_logs.call_id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_biz_agent_llm_call_messages_call_id'), 'biz_agent_llm_call_messages', ['call_id'], unique=False)
    op.create_index(op.f('ix_biz_agent_llm_call_messages_id'), 'biz_agent_llm_call_messages', ['id'], unique=False)


def downgrade() -> None:
    """回滚 LLM 调用日志相关表"""
    op.drop_index(op.f('ix_biz_agent_llm_call_messages_id'), table_name='biz_agent_llm_call_messages')
    op.drop_index(op.f('ix_biz_agent_llm_call_messages_call_id'), table_name='biz_agent_llm_call_messages')
    op.drop_table('biz_agent_llm_call_messages')
    op.drop_index(op.f('ix_biz_agent_llm_call_logs_user_id'), table_name='biz_agent_llm_call_logs')
    op.drop_index(op.f('ix_biz_agent_llm_call_logs_trace_id'), table_name='biz_agent_llm_call_logs')
    op.drop_index(op.f('ix_biz_agent_llm_call_logs_session_id'), table_name='biz_agent_llm_call_logs')
    op.drop_index(op.f('ix_biz_agent_llm_call_logs_call_id'), table_name='biz_agent_llm_call_logs')
    op.drop_index(op.f('ix_biz_agent_llm_call_logs_agent_key'), table_name='biz_agent_llm_call_logs')
    op.drop_table('biz_agent_llm_call_logs')
