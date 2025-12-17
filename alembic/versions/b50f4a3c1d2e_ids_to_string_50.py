"""convert ids to string(50)

Revision ID: b50f4a3c1d2e
Revises: 4c3a1f2e8a9b
Create Date: 2025-12-17 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b50f4a3c1d2e"
down_revision: Union[str, None] = "4c3a1f2e8a9b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """将主键/外键统一调整为 String(50)。"""
    # 先删除依赖的外键
    op.drop_constraint(
        "biz_agent_appointments_user_id_fkey",
        "biz_agent_appointments",
        type_="foreignkey",
    )
    op.drop_constraint(
        "biz_agent_blood_pressure_records_user_id_fkey",
        "biz_agent_blood_pressure_records",
        type_="foreignkey",
    )

    # 用户表
    op.execute(
        "ALTER TABLE biz_agent_users ALTER COLUMN id TYPE VARCHAR(50) USING id::text"
    )

    # 预约表
    op.execute(
        "ALTER TABLE biz_agent_appointments ALTER COLUMN id TYPE VARCHAR(50) USING id::text"
    )
    op.execute(
        "ALTER TABLE biz_agent_appointments ALTER COLUMN user_id TYPE VARCHAR(50) USING user_id::text"
    )

    # 血压表
    op.execute(
        "ALTER TABLE biz_agent_blood_pressure_records ALTER COLUMN id TYPE VARCHAR(50) USING id::text"
    )
    op.execute(
        "ALTER TABLE biz_agent_blood_pressure_records ALTER COLUMN user_id TYPE VARCHAR(50) USING user_id::text"
    )

    # LLM 调用日志主表
    op.execute(
        "ALTER TABLE biz_agent_llm_call_logs ALTER COLUMN id TYPE VARCHAR(50) USING id::text"
    )
    op.execute(
        "ALTER TABLE biz_agent_llm_call_logs ALTER COLUMN user_id TYPE VARCHAR(50) USING user_id::text"
    )

    # LLM 调用日志消息表
    op.execute(
        "ALTER TABLE biz_agent_llm_call_messages ALTER COLUMN id TYPE VARCHAR(50) USING id::text"
    )

    # 重建外键
    op.create_foreign_key(
        "fk_appointments_user",
        "biz_agent_appointments",
        "biz_agent_users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_bp_records_user",
        "biz_agent_blood_pressure_records",
        "biz_agent_users",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    # 由于字符串主键可能包含非数字字符，无法安全降级回整数
    raise RuntimeError("Downgrade not supported after converting IDs to String(50)")
