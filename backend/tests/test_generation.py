"""The rag generation path: topics, retrieval, citation validation, saving, and
the guarantees regenerate must keep. Gemini is faked throughout (fakes.py)."""

import asyncio
from unittest.mock import AsyncMock, patch

import fitz
import pytest

from backend import gemini
from backend.config import get_settings
from backend.embeddings import embed_documents
from backend.generation import (
    GenerationError,
    draft_cards,
    sample_chunks,
    validate_citations,
)
from backend.models import (
    Document,
    DocumentChunk,
    Flashcard,
    FlashcardSource,
    Interaction,
    QuizSession,
    User,
)
from conftest import MOCK_CARDS, _TestSession
from fakes import FakeGemini

TOPIC_TEXT = {
    "photosynthesis": "Photosynthesis in chloroplasts converts sunlight carbon dioxide and water into glucose and oxygen.",
    "french revolution": "The French Revolution began in 1789 with the storming of the Bastille in Paris.",
    "mitosis": "Mitosis divides a nucleus into two identical daughter nuclei during cell division.",
    "plate tectonics": "Plate tectonics moves lithosphere plates causing earthquakes volcanoes and mountains.",
    "keynesian economics": "Keynesian economics argues aggregate demand drives output and employment.",
}


@pytest.fixture()
def rag_mode(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "generation_mode", "rag")
    monkeypatch.setattr(settings, "rag_top_k", 2)
    monkeypatch.setattr(settings, "rag_topic_count", 5)
    monkeypatch.setattr(settings, "cards_per_upload", 15)
    # Small windows, so the five one-paragraph pages uploaded through the API
    # become several chunks rather than one.
    monkeypatch.setattr(settings, "chunk_target_tokens", 20)
    monkeypatch.setattr(settings, "chunk_max_tokens", 30)
    monkeypatch.setattr(settings, "chunk_overlap_tokens", 4)
    return settings


def _fake(monkeypatch, **kwargs):
    fake = FakeGemini(list(TOPIC_TEXT), **kwargs)
    monkeypatch.setattr(gemini, "generate_json", fake)
    return fake


def _seed_document(db, texts=None, user=None):
    if user is None:
        user = User(email="gen@example.com", email_verified=True)
        db.add(user)
        db.flush()
    texts = texts or list(TOPIC_TEXT.values())
    doc = Document(user_id=user.id, filename="bio.pdf", status="ready",
                   page_count=len(texts), extracted_text="\n".join(texts))
    db.add(doc)
    db.flush()
    for i, (t, v) in enumerate(zip(texts, embed_documents(texts))):
        db.add(DocumentChunk(document_id=doc.id, chunk_index=i, page_start=i + 1,
                             page_end=i + 1, text=t, token_count=len(t) // 4, embedding=v))
    db.commit()
    return user, doc


def _pdf(pages):
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(36, 36, 576, 806), text, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


# --- citation validation --------------------------------------------------------


@pytest.mark.parametrize("cited,expected", [
    ([3], [3]),
    ([3, 5], [3, 5]),
    ([5, 5, 3], [5, 3]),        # duplicates collapse, order kept
    (["3"], [3]),               # numeric strings are fine
    ([3.0], [3]),
])
def test_valid_citations_are_kept(cited, expected):
    assert validate_citations({"source_chunk_ids": cited}, [3, 5, 7]) == expected


@pytest.mark.parametrize("item", [
    {"source_chunk_ids": [3, 99]},  # one id outside the retrieved set
    {"source_chunk_ids": [99]},
    {"source_chunk_ids": []},
    {"source_chunk_ids": None},
    {},
    {"source_chunk_ids": "3"},       # not a list
    {"source_chunk_ids": [True]},
    {"source_chunk_ids": [3.5]},
    {"source_chunk_ids": ["three"]},
    "not a dict",
])
def test_invalid_citations_reject_the_card(item):
    assert validate_citations(item, [3, 5, 7]) is None


# --- topic sampling -------------------------------------------------------------


def test_sample_takes_everything_when_it_fits():
    chunks = [DocumentChunk(id=i, token_count=100) for i in range(5)]
    assert sample_chunks(chunks, 1000) == chunks


def test_sample_is_spread_across_the_document_and_within_budget():
    chunks = [DocumentChunk(id=i, token_count=500) for i in range(100)]
    picked = sample_chunks(chunks, 5000)
    assert sum(c.token_count for c in picked) <= 5000
    ids = [c.id for c in picked]
    assert ids[0] == 0 and ids[-1] >= 80  # reaches the back of the document
    assert ids == sorted(ids)


# --- the rag pipeline -------------------------------------------------------------


def test_rag_drafts_cards_citing_only_their_retrieved_chunks(db_session, rag_mode, monkeypatch):
    fake = _fake(monkeypatch)
    _, doc = _seed_document(db_session)

    result = asyncio.run(draft_cards(db_session, doc, full_generator=AsyncMock()))

    assert result.mode == "rag"
    assert len(result.cards) == 15
    assert result.topics == list(TOPIC_TEXT)
    assert not result.rejected
    by_topic = {}
    for card in result.cards:
        # The fake prefixes each question with the topic it was asked about,
        # so this catches any misalignment between topics and responses.
        assert card.question.startswith(f"{card.topic}:")
        assert card.chunk_ids
        assert set(card.chunk_ids) <= set(result.retrieved[card.topic])
        by_topic[card.topic] = by_topic.get(card.topic, 0) + 1
    # Round-robin: 15 cards over 5 topics is 3 each.
    assert sorted(by_topic.values()) == [3, 3, 3, 3, 3]
    # Each topic's best chunk is the one about it.
    chunk_text = {c.id: c.text for c in doc.chunks}
    for topic, ids in result.retrieved.items():
        assert chunk_text[ids[0]] == TOPIC_TEXT[topic]
    # The model only ever saw retrieved chunks in card prompts.
    for label, prompt in fake.prompts:
        if label == "rag:cards":
            assert prompt.count("<chunk id=") == rag_mode.rag_top_k


def test_cards_with_hallucinated_citations_are_dropped(db_session, rag_mode, monkeypatch):
    _fake(monkeypatch, hallucinate={"mitosis"})
    _, doc = _seed_document(db_session)

    result = asyncio.run(draft_cards(db_session, doc, full_generator=AsyncMock()))

    assert all(c.topic != "mitosis" for c in result.cards)
    assert result.rejected
    assert all(r["topic"] == "mitosis" for r in result.rejected)
    assert all(r["reason"] == "invalid or missing citations" for r in result.rejected)
    # Each topic is asked for one card over its share (ceil(15/5) + 1 = 4), so
    # the four surviving topics still fill the deck: 16 drafted, capped at 15.
    assert len(result.cards) == 15


def test_every_card_rejected_is_an_error(db_session, rag_mode, monkeypatch):
    _fake(monkeypatch, hallucinate=set(TOPIC_TEXT))
    _, doc = _seed_document(db_session)
    with pytest.raises(GenerationError, match="citation"):
        asyncio.run(draft_cards(db_session, doc, full_generator=AsyncMock()))


def test_retrieval_never_crosses_into_another_users_document(db_session, rag_mode, monkeypatch):
    fake = _fake(monkeypatch)
    user, doc = _seed_document(db_session, texts=[TOPIC_TEXT["photosynthesis"]])
    other = User(email="other@example.com", email_verified=True)
    db_session.add(other)
    db_session.flush()
    _, other_doc = _seed_document(db_session, user=other)

    result = asyncio.run(draft_cards(db_session, doc, full_generator=AsyncMock()))

    own_ids = {c.id for c in doc.chunks}
    assert {i for ids in result.retrieved.values() for i in ids} <= own_ids
    other_texts = set(TOPIC_TEXT.values()) - {TOPIC_TEXT["photosynthesis"]}
    for _, prompt in fake.prompts:
        assert not any(t in prompt for t in other_texts)


def test_rag_falls_back_to_full_for_a_document_without_chunks(db_session, rag_mode, monkeypatch):
    fake = _fake(monkeypatch)
    user = User(email="legacy@example.com", email_verified=True)
    db_session.add(user)
    db_session.flush()
    doc = Document(user_id=user.id, filename="old.pdf", status="ready", extracted_text="old text")
    db_session.add(doc)
    db_session.commit()

    full = AsyncMock(return_value=MOCK_CARDS)
    result = asyncio.run(draft_cards(db_session, doc, full_generator=full))

    assert result.mode == "full"
    assert result.fallback_reason
    full.assert_awaited_once()
    assert fake.prompts == []
    assert all(c.chunk_ids == [] for c in result.cards)


def test_full_mode_ignores_chunks(db_session, monkeypatch):
    fake = _fake(monkeypatch)
    _, doc = _seed_document(db_session)
    full = AsyncMock(return_value=MOCK_CARDS)

    result = asyncio.run(draft_cards(db_session, doc, full_generator=full))

    assert result.mode == "full"
    assert len(result.cards) == len(MOCK_CARDS)
    full.assert_awaited_once_with(doc.extracted_text, n=get_settings().cards_per_upload)
    assert fake.prompts == []


# --- through the API ----------------------------------------------------------------


def _upload(client, headers, pdf):
    import io

    resp = client.post(
        "/api/documents/upload",
        files={"file": ("notes.pdf", io.BytesIO(pdf), "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["doc_id"]


def test_rag_upload_saves_cards_with_citations(client, auth_headers, rag_mode, monkeypatch):
    _fake(monkeypatch)
    doc_id = _upload(client, auth_headers, _pdf(list(TOPIC_TEXT.values())))

    assert client.get(f"/api/documents/{doc_id}", headers=auth_headers).json()["status"] == "ready"
    db = _TestSession()
    try:
        cards = db.query(Flashcard).filter(Flashcard.doc_id == doc_id).all()
        assert len(cards) == 15
        for card in cards:
            assert card.sources
            assert all(s.chunk.document_id == doc_id for s in card.sources)
    finally:
        db.close()


def test_rag_upload_fails_cleanly_when_embedding_keeps_failing(
    client, auth_headers, rag_mode, monkeypatch
):
    from backend import embeddings
    from test_embeddings import _api_error

    _fake(monkeypatch)
    monkeypatch.setattr(embeddings, "_call_embed_api",
                        lambda *a, **k: (_ for _ in ()).throw(_api_error(400)))
    doc_id = _upload(client, auth_headers, _pdf(list(TOPIC_TEXT.values())))
    assert client.get(f"/api/documents/{doc_id}", headers=auth_headers).json()["status"] == "failed"


def test_rag_regenerate_preserves_interaction_history(client, auth_headers, rag_mode, monkeypatch):
    """The guarantee regenerate must keep in either mode: attempt history
    outlives the cards, and concepts are reused rather than duplicated."""
    _fake(monkeypatch)
    doc_id = _upload(client, auth_headers, _pdf(list(TOPIC_TEXT.values())))
    cards = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()

    client.post(f"/api/flashcards/{cards[0]['id']}/review", json={"known": True},
                headers=auth_headers)
    quiz = client.post("/api/quiz/start", json={"doc_id": doc_id, "num_questions": 1},
                       headers=auth_headers).json()
    client.post(f"/api/quiz/{quiz['quiz_id']}/answer",
                json={"answer": quiz["question"]["options"][0], "time_taken_seconds": 1.0},
                headers=auth_headers)
    before = client.get("/api/interactions/me", headers=auth_headers).json()
    db = _TestSession()
    try:
        chunk_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).count()
    finally:
        db.close()
    assert chunk_count > 1
    concepts_before = {c["key"] for c in client.get("/api/concepts/me", headers=auth_headers).json()}
    assert before["count"] == 2

    resp = client.post(f"/api/flashcards/{doc_id}/regenerate", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    new_ids = {c["id"] for c in resp.json()}
    assert len(new_ids) == 15
    assert not new_ids & {c["id"] for c in cards}

    after = client.get("/api/interactions/me", headers=auth_headers).json()
    assert after["count"] == 2
    assert [i["concept_id"] for i in after["interactions"]] == [
        i["concept_id"] for i in before["interactions"]
    ]
    assert all(i["flashcard_id"] is None for i in after["interactions"])
    concepts_after = {c["key"] for c in client.get("/api/concepts/me", headers=auth_headers).json()}
    assert concepts_after == concepts_before

    db = _TestSession()
    try:
        assert db.query(QuizSession).count() == 1
        assert db.query(Interaction).count() == 2
        # Old citations went with their cards; the chunks themselves stayed.
        live = {c.id for c in db.query(Flashcard).filter(Flashcard.doc_id == doc_id)}
        assert {s.flashcard_id for s in db.query(FlashcardSource)} == live
        assert db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).count() == chunk_count
    finally:
        db.close()


def test_a_failed_regenerate_keeps_the_existing_cards(client, auth_headers, rag_mode, monkeypatch):
    _fake(monkeypatch)
    doc_id = _upload(client, auth_headers, _pdf(list(TOPIC_TEXT.values())))
    before = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()

    _fake(monkeypatch, hallucinate=set(TOPIC_TEXT))  # every card will be rejected
    resp = client.post(f"/api/flashcards/{doc_id}/regenerate", headers=auth_headers)
    assert resp.status_code == 500
    assert "citation" in resp.json()["detail"]

    after = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()
    assert sorted(c["id"] for c in after) == sorted(c["id"] for c in before)
    assert client.get(f"/api/documents/{doc_id}", headers=auth_headers).json()["status"] == "ready"


def test_full_mode_regenerate_still_uses_the_full_generator(client, auth_headers, minimal_pdf,
                                                           monkeypatch):
    from conftest import upload_doc

    fake = _fake(monkeypatch)

    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    with patch("backend.routes.flashcards.generate_flashcards", new_callable=AsyncMock) as gen:
        gen.return_value = MOCK_CARDS
        resp = client.post(f"/api/flashcards/{doc_id}/regenerate", headers=auth_headers)
    assert resp.status_code == 200
    gen.assert_awaited_once()
    assert fake.prompts == []
