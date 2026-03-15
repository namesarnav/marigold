"""Integration tests for /api/quiz/* and /api/stats/me endpoints."""
import pytest

from conftest import MOCK_CARDS, upload_doc


@pytest.fixture()
def quiz_setup(client, auth_headers, minimal_pdf):
    """Returns (doc_id, auth_headers) with flashcards ready."""
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    return doc_id, auth_headers


def _start(client, headers, doc_id, num_questions=1):
    resp = client.post(
        "/api/quiz/start",
        json={"doc_id": doc_id, "num_questions": num_questions},
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# /api/quiz/start
# ---------------------------------------------------------------------------

def test_start_quiz_response_shape(client, quiz_setup):
    doc_id, headers = quiz_setup
    data = _start(client, headers, doc_id, num_questions=2)
    assert "quiz_id" in data
    q = data["question"]
    assert q["question_number"] == 1
    assert q["total_questions"] == 2
    assert isinstance(q["options"], list)
    assert len(q["options"]) > 0


def test_start_quiz_clamps_to_available_cards(client, quiz_setup):
    doc_id, headers = quiz_setup
    data = _start(client, headers, doc_id, num_questions=100)
    assert data["question"]["total_questions"] == len(MOCK_CARDS)


def test_start_quiz_doc_not_found(client, auth_headers):
    resp = client.post(
        "/api/quiz/start",
        json={"doc_id": 999, "num_questions": 5},
        headers=auth_headers,
    )
    assert resp.status_code == 404



# ---------------------------------------------------------------------------
# /api/quiz/{id}/answer
# ---------------------------------------------------------------------------

def test_answer_correct_completes_single_question_quiz(client, quiz_setup):
    doc_id, headers = quiz_setup
    start = _start(client, headers, doc_id, num_questions=1)
    quiz_id = start["quiz_id"]
    correct = MOCK_CARDS[0]["answer"]
    resp = client.post(
        f"/api/quiz/{quiz_id}/answer",
        json={"answer": correct, "time_taken_seconds": 5.0},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed"] is True


def test_answer_wrong_still_advances(client, quiz_setup):
    doc_id, headers = quiz_setup
    start = _start(client, headers, doc_id, num_questions=1)
    quiz_id = start["quiz_id"]
    resp = client.post(
        f"/api/quiz/{quiz_id}/answer",
        json={"answer": "totally wrong answer", "time_taken_seconds": 5.0},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["completed"] is True


def test_answer_multi_question_shows_next(client, quiz_setup):
    doc_id, headers = quiz_setup
    start = _start(client, headers, doc_id, num_questions=2)
    quiz_id = start["quiz_id"]
    resp = client.post(
        f"/api/quiz/{quiz_id}/answer",
        json={"answer": MOCK_CARDS[0]["answer"], "time_taken_seconds": 3.0},
        headers=headers,
    ).json()
    assert resp["completed"] is False
    assert resp["question"]["question_number"] == 2


# ---------------------------------------------------------------------------
# /api/quiz/{id}/skip
# ---------------------------------------------------------------------------

def test_skip_question(client, quiz_setup):
    doc_id, headers = quiz_setup
    start = _start(client, headers, doc_id, num_questions=1)
    quiz_id = start["quiz_id"]
    resp = client.post(
        f"/api/quiz/{quiz_id}/skip",
        json={"time_taken_seconds": 30.0},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["completed"] is True


# ---------------------------------------------------------------------------
# Full quiz flow + results
# ---------------------------------------------------------------------------

def test_full_quiz_perfect_score(client, quiz_setup):
    doc_id, headers = quiz_setup
    num_q = len(MOCK_CARDS)
    quiz_id = _start(client, headers, doc_id, num_questions=num_q)["quiz_id"]

    for card in MOCK_CARDS:
        client.post(
            f"/api/quiz/{quiz_id}/answer",
            json={"answer": card["answer"], "time_taken_seconds": 5.0},
            headers=headers,
        )

    results = client.get(f"/api/quiz/{quiz_id}/results", headers=headers).json()
    assert results["score"] == num_q
    assert results["total"] == num_q
    assert results["percentage"] == 100.0
    assert results["wrong_answers"] == []


def test_full_quiz_zero_score(client, quiz_setup):
    doc_id, headers = quiz_setup
    num_q = len(MOCK_CARDS)
    quiz_id = _start(client, headers, doc_id, num_questions=num_q)["quiz_id"]

    for _ in MOCK_CARDS:
        client.post(
            f"/api/quiz/{quiz_id}/answer",
            json={"answer": "intentionally wrong", "time_taken_seconds": 5.0},
            headers=headers,
        )

    results = client.get(f"/api/quiz/{quiz_id}/results", headers=headers).json()
    assert results["score"] == 0
    assert results["total"] == num_q
    assert len(results["wrong_answers"]) == num_q


def test_results_not_found(client, auth_headers):
    resp = client.get("/api/quiz/999/results", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /api/quiz/{id}/review
# ---------------------------------------------------------------------------

def test_review_after_quiz(client, quiz_setup):
    doc_id, headers = quiz_setup
    quiz_id = _start(client, headers, doc_id, num_questions=1)["quiz_id"]
    client.post(
        f"/api/quiz/{quiz_id}/skip",
        json={"time_taken_seconds": 5.0},
        headers=headers,
    )
    review = client.get(f"/api/quiz/{quiz_id}/review", headers=headers).json()
    assert "questions" in review
    assert len(review["questions"]) == 1
    q = review["questions"][0]
    assert "question" in q
    assert "correct_answer" in q
    assert "user_answer" in q
    assert "is_correct" in q


# ---------------------------------------------------------------------------
# /api/quiz/history
# ---------------------------------------------------------------------------

def test_quiz_history_empty(client, auth_headers):
    resp = client.get("/api/quiz/history", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_quiz_history_after_completion(client, quiz_setup):
    doc_id, headers = quiz_setup
    quiz_id = _start(client, headers, doc_id, num_questions=1)["quiz_id"]
    client.post(
        f"/api/quiz/{quiz_id}/answer",
        json={"answer": MOCK_CARDS[0]["answer"], "time_taken_seconds": 5.0},
        headers=headers,
    )
    history = client.get("/api/quiz/history", headers=headers).json()
    assert len(history) == 1
    item = history[0]
    assert item["score"] == 1
    assert item["total"] == 1
    assert item["percentage"] == 100.0
    assert item["doc_filename"] == "notes.pdf"


# ---------------------------------------------------------------------------
# /api/stats/me
# ---------------------------------------------------------------------------

def test_stats_initial(client, auth_headers):
    resp = client.get("/api/stats/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_quizzes"] == 0
    assert data["streak"] == 0
    assert data["total_flashcards_reviewed"] == 0


def test_stats_after_quiz(client, quiz_setup):
    doc_id, headers = quiz_setup
    # Viewing flashcards bumps flashcards_reviewed
    client.get(f"/api/flashcards/{doc_id}", headers=headers)

    # Complete a quiz
    quiz_id = _start(client, headers, doc_id, num_questions=1)["quiz_id"]
    client.post(
        f"/api/quiz/{quiz_id}/answer",
        json={"answer": MOCK_CARDS[0]["answer"], "time_taken_seconds": 3.0},
        headers=headers,
    )

    stats = client.get("/api/stats/me", headers=headers).json()
    assert stats["total_quizzes"] == 1
    assert stats["streak"] == 1
    assert stats["total_flashcards_reviewed"] > 0
    assert stats["average_score"] == 100


def test_stats_requires_auth(client):
    resp = client.get("/api/stats/me")
    assert resp.status_code == 401
