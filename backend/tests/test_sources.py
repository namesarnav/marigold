"""Citations in API responses: card lists, regenerate, and quiz review."""

from backend.sources import SNIPPET_CHARS, snippet
from conftest import upload_doc
from test_generation import TOPIC_TEXT, _fake, _pdf, _upload, rag_mode  # noqa: F401


def test_snippet_keeps_short_text_whole():
    assert snippet("  Short   text.\n") == "Short text."


def test_snippet_cuts_long_text_on_a_word_boundary():
    text = " ".join(["word"] * 200)
    out = snippet(text)
    assert len(out) <= SNIPPET_CHARS + 1
    assert out.endswith("…")
    assert out[:-1].split()[-1] == "word"


def test_rag_cards_carry_their_sources(client, auth_headers, rag_mode, monkeypatch):  # noqa: F811
    _fake(monkeypatch)
    doc_id = _upload(client, auth_headers, _pdf(list(TOPIC_TEXT.values())))

    cards = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()
    assert len(cards) == 15
    for card in cards:
        assert card["sources"], card
        for source in card["sources"]:
            assert set(source) == {"chunk_id", "page_start", "page_end", "snippet"}
            assert 1 <= source["page_start"] <= source["page_end"] <= 5
            assert source["snippet"]
    # The fake answers with the start of the first chunk it cites, so the
    # answer must be visible in that source's snippet.
    for card in cards:
        assert any(card["answer"][:40] in s["snippet"] for s in card["sources"])


def test_regenerate_response_carries_sources(client, auth_headers, rag_mode, monkeypatch):  # noqa: F811
    _fake(monkeypatch)
    doc_id = _upload(client, auth_headers, _pdf(list(TOPIC_TEXT.values())))
    resp = client.post(f"/api/flashcards/{doc_id}/regenerate", headers=auth_headers)
    assert resp.status_code == 200
    assert all(card["sources"] for card in resp.json())


def test_full_mode_cards_have_empty_sources(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    cards = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()
    assert cards and all(card["sources"] == [] for card in cards)


def test_quiz_review_includes_sources_but_quiz_questions_do_not(
    client, auth_headers, rag_mode, monkeypatch  # noqa: F811
):
    _fake(monkeypatch)
    doc_id = _upload(client, auth_headers, _pdf(list(TOPIC_TEXT.values())))
    quiz = client.post("/api/quiz/start", json={"doc_id": doc_id, "num_questions": 2},
                       headers=auth_headers).json()
    # During the quiz the source would give the answer away.
    assert "sources" not in quiz["question"]

    step = client.post(f"/api/quiz/{quiz['quiz_id']}/answer",
                       json={"answer": "nope", "time_taken_seconds": 1.0},
                       headers=auth_headers).json()
    assert "sources" not in step["question"]
    client.post(f"/api/quiz/{quiz['quiz_id']}/skip", json={"time_taken_seconds": 1.0},
                headers=auth_headers)

    review = client.get(f"/api/quiz/{quiz['quiz_id']}/review", headers=auth_headers).json()
    assert len(review["questions"]) == 2
    assert all(q["sources"] for q in review["questions"])
