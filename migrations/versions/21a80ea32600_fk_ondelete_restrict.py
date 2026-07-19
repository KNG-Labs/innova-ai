"""fk ondelete restrict

Revision ID: 21a80ea32600
Revises: ee6e74045934
Create Date: 2026-06-19 22:04:08.732587

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "21a80ea32600"
down_revision: Union[str, Sequence[str], None] = "ee6e74045934"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "dialog_sessions_user_id_fkey", "dialog_sessions", type_="foreignkey"
    )
    op.create_foreign_key(
        "dialog_sessions_user_id_fkey",
        "dialog_sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("messages_session_id_fkey", "messages", type_="foreignkey")
    op.create_foreign_key(
        "messages_session_id_fkey",
        "messages",
        "dialog_sessions",
        ["session_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("leads_user_id_fkey", "leads", type_="foreignkey")
    op.create_foreign_key(
        "leads_user_id_fkey",
        "leads",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("leads_session_id_fkey", "leads", type_="foreignkey")
    op.create_foreign_key(
        "leads_session_id_fkey",
        "leads",
        "dialog_sessions",
        ["session_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("leads_session_id_fkey", "leads", type_="foreignkey")
    op.create_foreign_key(
        "leads_session_id_fkey",
        "leads",
        "dialog_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("leads_user_id_fkey", "leads", type_="foreignkey")
    op.create_foreign_key(
        "leads_user_id_fkey",
        "leads",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("messages_session_id_fkey", "messages", type_="foreignkey")
    op.create_foreign_key(
        "messages_session_id_fkey",
        "messages",
        "dialog_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "dialog_sessions_user_id_fkey", "dialog_sessions", type_="foreignkey"
    )
    op.create_foreign_key(
        "dialog_sessions_user_id_fkey",
        "dialog_sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
