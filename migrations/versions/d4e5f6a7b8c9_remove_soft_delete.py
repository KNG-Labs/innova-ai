"""remove soft delete

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-09-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    has_soft_deleted_rows = op.get_bind().execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1 FROM users WHERE deleted_at IS NOT NULL
                UNION ALL
                SELECT 1 FROM dialog_sessions WHERE deleted_at IS NOT NULL
                UNION ALL
                SELECT 1 FROM messages WHERE deleted_at IS NOT NULL
                UNION ALL
                SELECT 1 FROM leads WHERE deleted_at IS NOT NULL
            )
            """
        )
    )
    if has_soft_deleted_rows.scalar():
        raise RuntimeError("soft-deleted rows must be resolved before migration")

    op.drop_index("uq_users_channel_anonymous_id", table_name="users")
    op.create_unique_constraint(
        "uq_users_channel_anonymous_id", "users", ["channel", "anonymous_id"]
    )
    op.drop_column("users", "deleted_at")
    op.drop_column("messages", "deleted_at")
    op.drop_column("leads", "deleted_at")
    op.drop_column("dialog_sessions", "deleted_at")


def downgrade() -> None:
    op.add_column(
        "dialog_sessions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "leads", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "messages", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.drop_constraint("uq_users_channel_anonymous_id", "users", type_="unique")
    op.create_index(
        "uq_users_channel_anonymous_id",
        "users",
        ["channel", "anonymous_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
