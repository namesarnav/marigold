"""document chunks, embeddings, and flashcard citations

Revision ID: 7c1d2e9a4b30
Revises: 29e635f561ab
Create Date: 2026-10-07

Adds what retrieval-augmented card generation needs:

* the pgvector extension;
* `document_chunks` — overlapping windows of a document's text with the pages
  they span and a vector(EMBEDDING_DIM) embedding, HNSW-indexed for cosine
  distance;
* `flashcard_sources` — which chunks each card was generated from.

Fails loudly when pgvector is not installed on the server. That is deliberate:
Railway's default Postgres template does not ship it, and a migration that
skipped the extension would boot an API whose uploads then fail one by one at
runtime. See the README section "Postgres with pgvector".

Purely additive. Nothing existing is altered or dropped, and `interactions`
is not touched: its foreign keys stay ON DELETE SET NULL.

The vector width is written out literally rather than imported from config, so
this file keeps describing the schema it created even if EMBEDDING_DIM changes
later (which would need its own migration).
"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa


revision: str = "7c1d2e9a4b30"
down_revision: Union[str, Sequence[str], None] = "29e635f561ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 768


def _require_pgvector() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError(
            "document_chunks needs PostgreSQL with the pgvector extension; "
            f"this database is {bind.dialect.name!r}."
        )
    available = bind.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
    ).scalar()
    if not available:
        raise RuntimeError(
            "The pgvector extension ('vector') is not installed on this Postgres "
            "server, so this migration cannot run. Railway's default Postgres "
            "template does not include it: switch to a pgvector-enabled Postgres "
            "(see README, 'Postgres with pgvector') and deploy again."
        )


def upgrade() -> None:
    _require_pgvector()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(EMBEDDING_DIM), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Leads with document_id, so it doubles as the index for "this
        # document's chunks" — the filter every retrieval query applies.
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
    )
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "flashcard_sources",
        sa.Column("flashcard_id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["flashcard_id"], ["flashcards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("flashcard_id", "chunk_id"),
    )
    op.create_index(
        op.f("ix_flashcard_sources_chunk_id"), "flashcard_sources", ["chunk_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_flashcard_sources_chunk_id"), table_name="flashcard_sources")
    op.drop_table("flashcard_sources")
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_table("document_chunks")
    # The extension is left installed. Other database objects may come to
    # depend on it, and dropping an extension is not this migration's business
    # to undo; re-running upgrade() is a no-op for it either way.
