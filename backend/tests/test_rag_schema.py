"""Schema guarantees for document chunks and flashcard citations.

The deletes below go through the ORM one row at a time, the way the app does
it. What is being checked is what the *database* does underneath: chunks and
citations are removed by ON DELETE CASCADE, and interaction history survives
because interactions.flashcard_id is ON DELETE SET NULL.
"""

from sqlalchemy import text

from backend.config import EMBEDDING_DIM
from backend.models import (
    Document,
    DocumentChunk,
    Flashcard,
    FlashcardSource,
    Interaction,
    User,
)


def _seed(db):
    user = User(email="schema@example.com", email_verified=True)
    db.add(user)
    db.flush()
    doc = Document(user_id=user.id, filename="a.pdf", status="ready", page_count=2)
    db.add(doc)
    db.flush()
    chunks = [
        DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            page_start=i + 1,
            page_end=i + 1,
            text=f"chunk {i}",
            token_count=2,
            embedding=[float(i == j) for j in range(EMBEDDING_DIM)],
        )
        for i in range(2)
    ]
    db.add_all(chunks)
    db.flush()
    card = Flashcard(doc_id=doc.id, question="Q?", answer="A", topic="T")
    db.add(card)
    db.flush()
    db.add_all([FlashcardSource(flashcard_id=card.id, chunk_id=c.id) for c in chunks])
    interaction = Interaction(
        user_id=user.id, flashcard_id=card.id, source="study", correct=True
    )
    db.add(interaction)
    db.commit()
    return user, doc, chunks, card, interaction


def _count(db, table):
    return db.execute(text(f"SELECT count(*) FROM {table}")).scalar()


def test_embedding_round_trips_at_the_configured_width(db_session):
    _, _, chunks, _, _ = _seed(db_session)
    db_session.expire_all()
    stored = db_session.get(DocumentChunk, chunks[1].id).embedding
    assert len(stored) == EMBEDDING_DIM
    assert stored[1] == 1.0 and stored[0] == 0.0


def test_deleting_a_card_removes_its_citations_but_keeps_chunks_and_history(db_session):
    _, _, _, card, interaction = _seed(db_session)

    db_session.delete(card)
    db_session.commit()

    assert _count(db_session, "flashcard_sources") == 0
    assert _count(db_session, "document_chunks") == 2
    db_session.expire_all()
    survivor = db_session.get(Interaction, interaction.id)
    assert survivor is not None
    assert survivor.flashcard_id is None


def test_deleting_a_document_cascades_chunks_and_citations_but_keeps_history(db_session):
    _, doc, _, _, interaction = _seed(db_session)

    db_session.delete(doc)
    db_session.commit()

    assert _count(db_session, "documents") == 0
    assert _count(db_session, "document_chunks") == 0
    assert _count(db_session, "flashcard_sources") == 0
    db_session.expire_all()
    survivor = db_session.get(Interaction, interaction.id)
    assert survivor is not None
    assert survivor.flashcard_id is None


def test_hnsw_cosine_index_exists(db_session):
    indexdef = db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'ix_document_chunks_embedding_hnsw'"
        )
    ).scalar()
    assert indexdef is not None
    assert "hnsw" in indexdef and "vector_cosine_ops" in indexdef
