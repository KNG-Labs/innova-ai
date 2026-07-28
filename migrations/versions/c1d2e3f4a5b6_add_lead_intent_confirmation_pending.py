"""add lead intent confirmation pending flag

Revision ID: c1d2e3f4a5b6
Revises: b4a91e6127c0
Create Date: 2026-07-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b4a91e6127c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dialog_sessions",
        sa.Column(
            "lead_intent_confirmation_pending",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("dialog_sessions", "lead_intent_confirmation_pending")
