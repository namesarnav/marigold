from unittest.mock import AsyncMock, patch

import pytest

from backend.concepts import normalize_concept_key, seconds_to_ms
from conftest import MOCK_CARDS, register_and_verify, upload_doc


def _register(client, email, name):
    """Register + verify a user and return Bearer headers for them."""
    return register_and_verify(client, email, name)


# --- unit: concept keys ---------------------------------------------------

@pytest.mark.parametrize(
    "label,expected",
    [
        ("Photosynthesis", "photosynthesis"),
        ("  Photosynthesis  ", "photosynthesis"),
        ("PHOTOSYNTHESIS", "photosynthesis"),
        ("Photosynthesis!", "photosynthesis"),
        ("Cell   Biology", "cell biology"),
        ("...Krebs Cycle...", "krebs cycle"),
        ("", ""),
        ("   ", ""),
        ("!!!", ""),
    ],
)
def test_normalize_concept_key(label, expected):
    assert normalize_concept_key(label) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [(None, None), (0, 0), (1.5, 1500), (12.3456, 12346), (-4.0, 0)],
)
def test_seconds_to_ms(seconds, expected):
    assert seconds_to_ms(seconds) == expected


# --- concept assignment ---------------------------------------------------

def test_upload_groups_cards_sharing_a_topic_into_one_concept(
    client, auth_headers, minimal_pdf
):
    """All three MOCK_CARDS carry topic "Python", so they are one concept."""
    upload_doc(client, auth_headers, minimal_pdf)

    concepts = client.get("/api/concepts/me", headers=auth_headers).json()
    assert len(concepts) == 1
    assert concepts[0]["label"] == "Python"
    assert concepts[0]["key"] == "topic:python"
    assert concepts[0]["source"] == "topic"
    assert concepts[0]["card_count"] == len(MOCK_CARDS)


def test_same_topic_across_two_documents_is_one_concept(
    client, auth_headers, minimal_pdf
):
    """This is the point of concepts: forgetting generalizes across documents."""
    upload_doc(client, auth_headers, minimal_pdf, filename="week1.pdf")
    upload_doc(client, auth_headers, minimal_pdf, filename="week2.pdf")

    concepts = client.get("/api/concepts/me", headers=auth_headers).json()
    assert len(concepts) == 1
    assert concepts[0]["card_count"] == len(MOCK_CARDS) * 2


def test_cards_are_not_shared_between_users(client, minimal_pdf):
    """Concepts are per-user: two users studying "Python" get separate rows."""
    ha = _register(client, "a@example.com", "A")
    hb = _register(client, "b@example.com", "B")

    upload_doc(client, ha, minimal_pdf)
    upload_doc(client, hb, minimal_pdf)

    ca = client.get("/api/concepts/me", headers=ha).json()
    cb = client.get("/api/concepts/me", headers=hb).json()
    assert len(ca) == 1 and len(cb) == 1
    assert ca[0]["id"] != cb[0]["id"]


def test_card_without_a_topic_falls_back_to_a_document_concept(
    client, auth_headers, minimal_pdf
):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    resp = client.post(
        f"/api/flashcards/{doc_id}/new",
        json={"question": "Untagged?", "answer": "Yes", "topic": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    concepts = client.get("/api/concepts/me", headers=auth_headers).json()
    fallbacks = [c for c in concepts if c["source"] == "document"]
    assert len(fallbacks) == 1
    assert fallbacks[0]["key"] == f"document:{doc_id}"
    assert fallbacks[0]["label"] == "notes.pdf"


def test_editing_a_topic_moves_the_card_to_another_concept(
    client, auth_headers, minimal_pdf
):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    card_id = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()[0]["id"]

    resp = client.patch(
        f"/api/flashcards/{card_id}", json={"topic": "Data Structures"}, headers=auth_headers
    )
    assert resp.status_code == 200

    concepts = {c["key"]: c for c in client.get("/api/concepts/me", headers=auth_headers).json()}
    assert set(concepts) == {"topic:python", "topic:data structures"}
    assert concepts["topic:python"]["card_count"] == len(MOCK_CARDS) - 1
    assert concepts["topic:data structures"]["card_count"] == 1


# --- interaction logging from quizzes -------------------------------------

def _start_quiz(client, headers, doc_id, n=1):
    resp = client.post(
        "/api/quiz/start", json={"doc_id": doc_id, "num_questions": n}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_correct_answer_logs_an_interaction(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    quiz = _start_quiz(client, auth_headers, doc_id)
    correct = MOCK_CARDS[0]["answer"]

    client.post(
        f"/api/quiz/{quiz['quiz_id']}/answer",
        json={"answer": correct, "time_taken_seconds": 4.2},
        headers=auth_headers,
    )

    seq = client.get("/api/interactions/me", headers=auth_headers).json()
    assert seq["count"] == 1
    row = seq["interactions"][0]
    assert row["correct"] is True
    assert row["source"] == "quiz"
    assert row["response_time_ms"] == 4200
    assert row["concept_id"] is not None
    assert row["flashcard_id"] == quiz["question"]["question_id"]


def test_wrong_answer_logs_correct_false(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    quiz = _start_quiz(client, auth_headers, doc_id)

    client.post(
        f"/api/quiz/{quiz['quiz_id']}/answer",
        json={"answer": "definitely not the answer", "time_taken_seconds": 9.0},
        headers=auth_headers,
    )

    seq = client.get("/api/interactions/me", headers=auth_headers).json()
    assert seq["interactions"][0]["correct"] is False


def test_skip_logs_correct_none_not_false(client, auth_headers, minimal_pdf):
    """A skip is absence of evidence, not evidence of forgetting."""
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    quiz = _start_quiz(client, auth_headers, doc_id)

    client.post(
        f"/api/quiz/{quiz['quiz_id']}/skip",
        json={"time_taken_seconds": 30.0},
        headers=auth_headers,
    )

    seq = client.get("/api/interactions/me", headers=auth_headers).json()
    assert seq["count"] == 1
    assert seq["interactions"][0]["correct"] is None
    assert seq["interactions"][0]["response_time_ms"] == 30000


def test_full_quiz_logs_one_interaction_per_question(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    quiz = _start_quiz(client, auth_headers, doc_id, n=len(MOCK_CARDS))
    quiz_id = quiz["quiz_id"]

    answers = {c["question"]: c["answer"] for c in MOCK_CARDS}
    question = quiz["question"]
    while question is not None:
        resp = client.post(
            f"/api/quiz/{quiz_id}/answer",
            json={"answer": answers[question["text"]], "time_taken_seconds": 2.0},
            headers=auth_headers,
        ).json()
        question = resp.get("question")

    seq = client.get("/api/interactions/me", headers=auth_headers).json()
    assert seq["count"] == len(MOCK_CARDS)
    assert all(r["correct"] is True for r in seq["interactions"])
    # Every card shared topic "Python", so all attempts land on one concept.
    assert len({r["concept_id"] for r in seq["interactions"]}) == 1


# --- interaction logging from study mode ----------------------------------

def test_study_review_logs_a_study_interaction(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    card_id = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()[0]["id"]

    resp = client.post(
        f"/api/flashcards/{card_id}/review",
        json={"known": True, "response_time_ms": 1800},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["concept_id"] is not None

    seq = client.get("/api/interactions/me", headers=auth_headers).json()
    assert seq["count"] == 1
    row = seq["interactions"][0]
    assert row["source"] == "study"
    assert row["correct"] is True
    assert row["response_time_ms"] == 1800


def test_study_review_can_record_not_known(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    card_id = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()[0]["id"]

    client.post(
        f"/api/flashcards/{card_id}/review", json={"known": False}, headers=auth_headers
    )

    row = client.get("/api/interactions/me", headers=auth_headers).json()["interactions"][0]
    assert row["correct"] is False
    assert row["response_time_ms"] is None


def test_study_review_rejects_negative_response_time(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    card_id = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()[0]["id"]

    resp = client.post(
        f"/api/flashcards/{card_id}/review",
        json={"known": True, "response_time_ms": -1},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_study_review_on_another_users_card_is_404(client, minimal_pdf):
    ho = _register(client, "owner@example.com", "O")
    hi = _register(client, "intruder@example.com", "I")

    doc_id = upload_doc(client, ho, minimal_pdf)
    card_id = client.get(f"/api/flashcards/{doc_id}", headers=ho).json()[0]["id"]

    resp = client.post(
        f"/api/flashcards/{card_id}/review", json={"known": True}, headers=hi
    )
    assert resp.status_code == 404


# --- reading the sequence -------------------------------------------------

def test_sequence_is_ordered_oldest_first(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    cards = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()

    for card in cards:
        client.post(
            f"/api/flashcards/{card['id']}/review",
            json={"known": True},
            headers=auth_headers,
        )

    seq = client.get("/api/interactions/me", headers=auth_headers).json()
    ids = [r["id"] for r in seq["interactions"]]
    assert ids == sorted(ids)
    assert [r["responded_at"] for r in seq["interactions"]] == sorted(
        r["responded_at"] for r in seq["interactions"]
    )


def test_sequence_limit_returns_the_most_recent_window(
    client, auth_headers, minimal_pdf
):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    cards = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()
    for card in cards:
        client.post(
            f"/api/flashcards/{card['id']}/review",
            json={"known": True},
            headers=auth_headers,
        )

    everything = client.get("/api/interactions/me", headers=auth_headers).json()
    windowed = client.get("/api/interactions/me?limit=2", headers=auth_headers).json()

    assert windowed["count"] == 2
    # The newest two, still in ascending order.
    assert [r["id"] for r in windowed["interactions"]] == [
        r["id"] for r in everything["interactions"][-2:]
    ]


def test_sequence_limit_is_bounded(client, auth_headers):
    assert client.get("/api/interactions/me?limit=0", headers=auth_headers).status_code == 422
    assert (
        client.get("/api/interactions/me?limit=999999", headers=auth_headers).status_code
        == 422
    )


def test_interactions_require_auth(client):
    assert client.get("/api/interactions/me").status_code == 401
    assert client.get("/api/concepts/me").status_code == 401


def test_a_user_only_sees_their_own_interactions(client, minimal_pdf):
    ha = _register(client, "sa@example.com", "A")
    hb = _register(client, "sb@example.com", "B")

    doc_id = upload_doc(client, ha, minimal_pdf)
    card_id = client.get(f"/api/flashcards/{doc_id}", headers=ha).json()[0]["id"]
    client.post(f"/api/flashcards/{card_id}/review", json={"known": True}, headers=ha)

    assert client.get("/api/interactions/me", headers=ha).json()["count"] == 1
    assert client.get("/api/interactions/me", headers=hb).json()["count"] == 0


def test_concept_interaction_counts_track_attempts(client, auth_headers, minimal_pdf):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    cards = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()

    assert client.get("/api/concepts/me", headers=auth_headers).json()[0][
        "interaction_count"
    ] == 0

    for card in cards[:2]:
        client.post(
            f"/api/flashcards/{card['id']}/review",
            json={"known": True},
            headers=auth_headers,
        )

    assert client.get("/api/concepts/me", headers=auth_headers).json()[0][
        "interaction_count"
    ] == 2


# --- durability -----------------------------------------------------------

def test_history_survives_deleting_the_card_it_came_from(
    client, auth_headers, minimal_pdf
):
    """Interactions are an event log: deleting a card must not rewrite history."""
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    card_id = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()[0]["id"]
    client.post(f"/api/flashcards/{card_id}/review", json={"known": True}, headers=auth_headers)

    before = client.get("/api/interactions/me", headers=auth_headers).json()
    concept_id = before["interactions"][0]["concept_id"]

    assert client.delete(f"/api/flashcards/{card_id}", headers=auth_headers).status_code == 204

    after = client.get("/api/interactions/me", headers=auth_headers).json()
    assert after["count"] == 1
    # The concept the attempt was against is still attributable.
    assert after["interactions"][0]["concept_id"] == concept_id


def test_history_survives_regenerating_a_documents_cards(
    client, auth_headers, minimal_pdf
):
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    card_id = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()[0]["id"]
    client.post(f"/api/flashcards/{card_id}/review", json={"known": True}, headers=auth_headers)

    with patch(
        "backend.routes.flashcards.generate_flashcards", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = MOCK_CARDS
        resp = client.post(f"/api/flashcards/{doc_id}/regenerate", headers=auth_headers)
    assert resp.status_code == 200

    assert client.get("/api/interactions/me", headers=auth_headers).json()["count"] == 1
    # Regeneration reuses the existing concept rather than duplicating it.
    concepts = client.get("/api/concepts/me", headers=auth_headers).json()
    assert len(concepts) == 1
    assert concepts[0]["card_count"] == len(MOCK_CARDS)
