"""drop foreign keys and unique constraints

Revision ID: c7c4d9b1c9f3
Revises: b50f4a3c1d2e
Create Date: 2025-12-17 15:55:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c7c4d9b1c9f3"
down_revision: Union[str, None] = "b50f4a3c1d2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """移除外键约束与非主键唯一约束/索引。"""
    # ---- Drop foreign keys (if exist) ----
    op.execute(
        "ALTER TABLE biz_agent_appointments DROP CONSTRAINT IF EXISTS fk_appointments_user"
    )
    op.execute(
        "ALTER TABLE biz_agent_blood_pressure_records DROP CONSTRAINT IF EXISTS fk_bp_records_user"
    )
    op.execute(
        "ALTER TABLE biz_agent_appointments DROP CONSTRAINT IF EXISTS biz_agent_appointments_user_id_fkey"
    )
    op.execute(
        "ALTER TABLE biz_agent_blood_pressure_records DROP CONSTRAINT IF EXISTS biz_agent_blood_pressure_records_user_id_fkey"
    )
    op.execute(
        "ALTER TABLE biz_agent_llm_call_messages DROP CONSTRAINT IF EXISTS biz_agent_llm_call_messages_call_id_fkey"
    )

    # ---- Drop unique constraints / unique indexes ----
    op.execute(
        "ALTER TABLE biz_agent_llm_call_logs DROP CONSTRAINT IF EXISTS biz_agent_llm_call_logs_call_id_key"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_biz_agent_llm_call_logs_call_id"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_biz_agent_users_username"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_biz_agent_users_phone"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_biz_agent_users_email"
    )


def downgrade() -> None:
    raise RuntimeError("Downgrade not supported for dropping constraints/indexes")
