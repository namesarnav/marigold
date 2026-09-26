"""Retrieval is scoped to one document, ranked by similarity, and returns k rows
even when the HNSW index — not an exact scan — answers the query."""

import pytest
from sqlalchemy import text

from backend.embeddings import embed_documents, embed_query
from backend.models import Document, DocumentChunk, User
from backend.retrieval import retrieve_chunks

TOPICS = {
    "photosynthesis": "Photosynthesis in chloroplasts converts sunlight carbon dioxide and water into glucose and oxygen.",
    "revolution": "The French Revolution began in 1789 with the storming of the Bastille in Paris.",
    "mitosis": "Mitosis divides a nucleus into two identical daughter nuclei through prophase metaphase anaphase telophase.",
    "tectonics": "Plate tectonics moves lithosphere plates causing earthquakes volcanoes and mountain ranges.",
    "keynes": "Keynesian economics argues aggregate demand drives output and employment in the short run.",
}


def _make_doc(db, user, texts, name="doc.pdf"):
    doc = Document(user_id=user.id, filename=name, status="ready", page_count=len(texts))
    db.add(doc)
    db.flush()
    vectors = embed_documents(texts)
    for i, (t, v) in enumerate(zip(texts, vectors)):
        db.add(DocumentChunk(
            document_id=doc.id, chunk_index=i, page_start=i + 1, page_end=i + 1,
            text=t, token_count=len(t) // 4, embedding=v,
        ))
    db.flush()
    return doc


@pytest.fixture()
def user(db_session):
    u = User(email="retrieval@example.com", email_verified=True)
    db_session.add(u)
    db_session.flush()
    return u


def test_most_similar_chunk_ranks_first(db_session, user):
    doc = _make_doc(db_session, user, list(TOPICS.values()))
    results = retrieve_chunks(db_session, doc.id, embed_query("how does photosynthesis make glucose"), k=3)

    assert len(results) == 3
    assert results[0].chunk.text == TOPICS["photosynthesis"]
    distances = [r.distance for r in results]
    assert distances == sorted(distances)


def test_only_the_requested_documents_chunks_are_returned(db_session, user):
    """Another document holding the *exact* query text must not leak in."""
    query = "how does photosynthesis make glucose"
    target = _make_doc(db_session, user, [TOPICS["revolution"], TOPICS["keynes"]], "target.pdf")
    other_user = User(email="someone-else@example.com", email_verified=True)
    db_session.add(other_user)
    db_session.flush()
    _make_doc(db_session, other_user, [query, TOPICS["photosynthesis"]], "other.pdf")

    results = retrieve_chunks(db_session, target.id, embed_query(query), k=5)

    assert len(results) == 2  # all the target has; nothing from the other doc
    assert {r.chunk.document_id for r in results} == {target.id}


def test_unembedded_chunks_are_skipped(db_session, user):
    doc = _make_doc(db_session, user, [TOPICS["mitosis"]])
    db_session.add(DocumentChunk(
        document_id=doc.id, chunk_index=1, page_start=2, page_end=2,
        text="no vector yet", token_count=3, embedding=None,
    ))
    db_session.flush()
    results = retrieve_chunks(db_session, doc.id, embed_query("mitosis"), k=5)
    assert [r.chunk.chunk_index for r in results] == [0]


def test_k_zero_returns_nothing(db_session, user):
    doc = _make_doc(db_session, user, [TOPICS["mitosis"]])
    assert retrieve_chunks(db_session, doc.id, embed_query("mitosis"), k=0) == []


def _crowded_library(db, user, query):
    """30 documents x 20 chunks, every one closer to `query` than the target's.

    The shape that breaks index-based per-document search: plain HNSW returned
    0 of 5 rows here, and HNSW with iterative scanning ranked the target's best
    chunk first in only 15 of 20 runs (see backend/retrieval.py).
    """
    for d in range(30):
        _make_doc(db, user, [f"{query} variant {d} {i}" for i in range(20)], f"near-{d}.pdf")
    target = _make_doc(
        db, user,
        [f"{TOPICS['revolution']} section {i}" for i in range(10)] + [TOPICS["photosynthesis"]],
        "target.pdf",
    )
    db.commit()
    return target


def test_exact_top_k_among_many_documents_even_when_the_index_is_preferred(db_session, user):
    query = "photosynthesis chloroplasts sunlight glucose"
    target = _crowded_library(db_session, user, query)

    # Make every exact plan look expensive, so the planner would take the HNSW
    # index if the query let it.
    db_session.execute(text("SET LOCAL enable_seqscan = off"))
    db_session.execute(text("SET LOCAL enable_sort = off"))

    vector = embed_query(query)
    results = retrieve_chunks(db_session, target.id, vector, k=5)

    # Brute force over the target's chunks, in Python.
    chunks = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == target.id).all()
    def cosine_distance(a, b):
        return 1 - sum(x * y for x, y in zip(a, b))  # both unit length
    expected = sorted(chunks, key=lambda c: (cosine_distance(c.embedding, vector), c.id))[:5]

    assert [r.chunk.id for r in results] == [c.id for c in expected]
    assert results[0].chunk.text == TOPICS["photosynthesis"]
    assert {r.chunk.document_id for r in results} == {target.id}


def test_per_document_query_never_uses_the_hnsw_index(db_session, user):
    query = "photosynthesis chloroplasts sunlight glucose"
    target = _crowded_library(db_session, user, query)
    db_session.execute(text("SET LOCAL enable_seqscan = off"))
    db_session.execute(text("SET LOCAL enable_sort = off"))

    statements = []

    from sqlalchemy import event

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "scored" in statement:
            statements.append((statement, parameters))

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        retrieve_chunks(db_session, target.id, embed_query(query), k=5)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert len(statements) == 1
    sql, params = statements[0]
    plan = "\n".join(
        row[0] for row in db_session.connection().exec_driver_sql("EXPLAIN " + sql, params)
    )
    assert "hnsw" not in plan.lower(), plan
    assert "CTE" in plan, plan
