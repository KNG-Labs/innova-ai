"""create_knowledge_tables

Revision ID: 65bce8c2411d
Revises: a8ffd1220905
Create Date: 2026-06-22 14:04:45.639712

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.domain import EMBEDDING_DIM

revision: str = "65bce8c2411d"
down_revision: Union[str, Sequence[str], None] = "a8ffd1220905"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
