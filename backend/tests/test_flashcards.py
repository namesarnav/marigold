"""Integration tests for /api/flashcards/* endpoints."""
import pytest
from unittest.mock import AsyncMock, patch

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
