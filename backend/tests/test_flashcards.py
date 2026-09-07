"""Integration tests for /api/flashcards/* endpoints."""
import pytest
from unittest.mock import AsyncMock, patch

from sqlalchemy.exc import IntegrityError

from conftest import MOCK_CARDS, upload_doc


@pytest.fixture()
def doc_id(client, auth_headers, minimal_pdf):
    return upload_doc(client, auth_headers, minimal_pdf)


def test_get_flashcards_success(client, auth_headers, doc_id):
    resp = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers)
    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) == len(MOCK_CARDS)
    for card in cards:
        assert "id" in card
        assert "question" in card
        assert "answer" in card
        assert "options" in card
        assert len(card["options"]) > 0


def test_get_flashcards_options_include_answer(client, auth_headers, doc_id):
    cards = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()
    for card in cards:
        assert card["answer"] in card["options"]


def test_get_flashcards_document_not_found(client, auth_headers):
    resp = client.get("/api/flashcards/999", headers=auth_headers)
    assert resp.status_code == 404



def test_create_flashcard(client, auth_headers, doc_id):
    resp = client.post(
        f"/api/flashcards/{doc_id}/new",
        json={"question": "Manual Q?", "answer": "Manual A", "topic": "Testing"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["question"] == "Manual Q?"
    assert data["answer"] == "Manual A"
    assert data["topic"] == "Testing"


def test_create_flashcard_no_topic(client, auth_headers, doc_id):
    resp = client.post(
        f"/api/flashcards/{doc_id}/new",
        json={"question": "Q?", "answer": "A"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["topic"] is None


def test_create_flashcard_not_found_doc(client, auth_headers):
    resp = client.post(
        "/api/flashcards/999/new",
        json={"question": "Q?", "answer": "A"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_patch_flashcard_question(client, auth_headers, doc_id):
    cards = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()
    card_id = cards[0]["id"]
    resp = client.patch(
        f"/api/flashcards/{card_id}",
        json={"question": "Updated question?"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["question"] == "Updated question?"


def test_patch_flashcard_answer(client, auth_headers, doc_id):
    cards = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()
    card_id = cards[0]["id"]
    resp = client.patch(
        f"/api/flashcards/{card_id}",
        json={"answer": "Updated answer"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["answer"] == "Updated answer"


def test_patch_flashcard_not_found(client, auth_headers):
    resp = client.patch(
        "/api/flashcards/999",
        json={"question": "Q?"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_delete_flashcard(client, auth_headers, doc_id):
    cards = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()
    card_id = cards[0]["id"]
    resp = client.delete(f"/api/flashcards/{card_id}", headers=auth_headers)
    assert resp.status_code == 204
    # One fewer card
    remaining = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()
    assert len(remaining) == len(MOCK_CARDS) - 1


def test_delete_flashcard_not_found(client, auth_headers):
    resp = client.delete("/api/flashcards/999", headers=auth_headers)
    assert resp.status_code == 404


def test_database_error_reaches_a_cross_origin_caller(client, auth_headers, doc_id):
    """A 500 from a database error must carry CORS headers.

    Without them the browser will not expose the response to JavaScript at all:
    fetch rejects with "Failed to fetch", which reports a network failure for
    what is really a server error with a perfectly good status and message.
    That is how the regenerate bug above presented — the only account of it was
    in the container log.

    The header comes from CORSMiddleware, which unhandled exceptions bypass
    (ServerErrorMiddleware is outside it). So this asserts the handler in
    backend/main.py is wired in a way that keeps the response inside the stack.
    """
    with patch(
        "backend.routes.flashcards.generate_flashcards", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = MOCK_CARDS
        with patch(
            "backend.routes.flashcards.assign_concepts",
            side_effect=IntegrityError("boom", None, Exception("boom")),
        ):
            resp = client.post(
                f"/api/flashcards/{doc_id}/regenerate",
                headers={**auth_headers, "Origin": "http://localhost:5173"},
            )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "A database error occurred. Please try again."
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
    # The constraint and table names stay in the log, not the response body.
    assert "boom" not in resp.text


def test_regenerate_after_a_quiz(client, auth_headers, doc_id):
    """Regenerating a document whose cards have been answered in a quiz.

    Only meaningful against Postgres: SQLite does not enforce foreign keys by
    default, so the bulk `query(...).delete()` this guards against succeeded
    there and failed in production with

        ForeignKeyViolation: update or delete on table "flashcards" violates
        foreign key constraint "quiz_answers_flashcard_id_fkey"

    `Flashcard.quiz_answers` cascades, but only through the ORM — a bulk
    delete emits raw SQL and skips cascades entirely. Answering one question
    is enough to create the referencing row.
    """
    quiz = client.post(
        "/api/quiz/start",
        json={"doc_id": doc_id, "num_questions": 1},
        headers=auth_headers,
    ).json()
    answered = client.post(
        f"/api/quiz/{quiz['quiz_id']}/answer",
        json={"answer": quiz["question"]["options"][0], "time_taken_seconds": 1.0},
        headers=auth_headers,
    )
    assert answered.status_code == 200

    with patch(
        "backend.routes.flashcards.generate_flashcards", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = [
            {
                "question": "Fresh Q?",
                "answer": "Fresh A",
                "topic": "Fresh",
                "distractors": ["a", "b", "c"],
            }
        ]
        resp = client.post(f"/api/flashcards/{doc_id}/regenerate", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert [c["question"] for c in resp.json()] == ["Fresh Q?"]

    # The quiz session itself survives — its score is history, not a card.
    history = client.get("/api/quiz/history", headers=auth_headers).json()
    assert len(history) == 1


def test_regenerate_flashcards(client, auth_headers, doc_id):
    new_cards = [
        {
            "question": "Regenerated Q?",
            "answer": "Regenerated A",
            "topic": "Regen",
            "distractors": ["x", "y", "z"],
        }
    ]
    with patch(
        "backend.routes.flashcards.generate_flashcards", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = new_cards
        resp = client.post(f"/api/flashcards/{doc_id}/regenerate", headers=auth_headers)

    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) == 1
    assert cards[0]["question"] == "Regenerated Q?"
