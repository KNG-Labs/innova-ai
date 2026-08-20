"""add RAG context to dialog sessions

Revision ID: b4a91e6127c0
Revises: 7f3b2c9d1a01
Create Date: 2026-07-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b4a91e6127c0"
down_revision: Union[str, Sequence[str], None] = "7f3b2c9d1a01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dialog_sessions",
        sa.Column("last_rag_source_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "dialog_sessions",
        sa.Column("last_rag_source_title", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "dialog_sessions",
        sa.Column("expected_qualification_field", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_dialog_sessions_last_rag_source_id_knowledge_documents",
        "dialog_sessions",
        "knowledge_documents",
        ["last_rag_source_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_dialog_sessions_last_rag_source_id_knowledge_documents",
        "dialog_sessions",
        type_="foreignkey",
    )
    op.drop_column("dialog_sessions", "expected_qualification_field")
    op.drop_column("dialog_sessions", "last_rag_source_title")
    op.drop_column("dialog_sessions", "last_rag_source_id")
