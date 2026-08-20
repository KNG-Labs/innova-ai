"""track explicit contact refusals and opt-out

Revision ID: 7f3b2c9d1a01
Revises: 65bce8c2411d
Create Date: 2026-07-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "7f3b2c9d1a01"
down_revision: Union[str, Sequence[str], None] = "65bce8c2411d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "dialog_sessions",
        "contact_attempts",
        new_column_name="contact_refusals",
    )
    op.execute("UPDATE dialog_sessions SET contact_refusals = 0")
    op.add_column(
        "dialog_sessions",
        sa.Column(
            "contact_opt_out",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("dialog_sessions", "contact_opt_out")
    op.alter_column(
        "dialog_sessions",
        "contact_refusals",
        new_column_name="contact_attempts",
    )
