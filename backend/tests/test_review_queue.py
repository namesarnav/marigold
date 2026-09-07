"""`/api/review/next` — the knowledge-tracing model reaching the product.

Everything the interaction log was being collected for runs through here, and
this is the only place the backend touches `ml/`. The tests that matter are less
about the ordering itself — `ml/tests` covers the ranking maths in detail — and
more about the seam: that concept ids survive the round trip, that a naive
timestamp does not blow up the datetime arithmetic, and that a model failure
degrades into a usable queue instead of a 500.
"""

from datetime import datetime, timedelta, timezone

import pytest
from conftest import register_and_verify, upload_doc


def upload_with_topics(client, headers, pdf_bytes, topics, filename="other.pdf"):
    """Upload a document whose generated cards carry the given topics.

    `conftest.upload_doc` always returns MOCK_CARDS, which are all topic
    "Python" and therefore collapse into a single concept. Several tests here
    need more than one concept to say anything about ordering.
    """
    import io
    from unittest.mock import AsyncMock, patch

    cards = [
        {
            "question": f"Q about {t}?",
            "answer": f"A about {t}",
            "topic": t,
            "distractors": ["x", "y", "z"],
        }
        for t in topics
    ]
    with patch(
        "backend.routes.documents.generate_flashcards", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = cards
        resp = client.post(
            "/api/documents/upload",
            files={"file": (filename, io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["doc_id"]


@pytest.fixture
def studied(client, auth_headers, minimal_pdf):
    """A user with cards, one of which has been answered."""
    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    cards = client.get(f"/api/flashcards/{doc_id}", headers=auth_headers).json()
    client.post(
        f"/api/flashcards/{cards[0]['id']}/review",
        json={"known": True, "response_time_ms": 1800},
        headers=auth_headers,
    )
    return {"doc_id": doc_id, "cards": cards}


# --- the basics -------------------------------------------------------------

def test_an_account_with_no_concepts_gets_an_empty_queue(client, auth_headers):
    """A brand-new account must get an empty list, not an error."""
    resp = client.get("/api/review/next", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["concepts"] == []


def test_the_queue_lists_the_users_concepts(client, auth_headers, studied):
    resp = client.get("/api/review/next", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] > 0

    row = body["concepts"][0]
    # The ids have to survive int -> str -> int across the ml boundary; a
    # mismatch here would silently return the wrong concept's score.
    assert isinstance(row["concept_id"], int)
    assert row["label"]
    assert 0.0 <= row["p_correct"] <= 1.0
    assert row["source"] in {"prior", "blend", "sakt"}


def test_never_practised_concepts_are_included(client, auth_headers, minimal_pdf, studied):
    """A library nobody has studied yet must still produce a usable queue.

    Excluding unpractised concepts would leave a new user with an empty review
    feed, which is precisely when they most need one.
    """
    # A second document introducing a concept nobody has answered.
    upload_with_topics(client, auth_headers, minimal_pdf, ["Recursion"])

    body = client.get("/api/review/next", headers=auth_headers).json()

    unpractised = [c for c in body["concepts"] if c["interaction_count"] == 0]
    assert unpractised, body["concepts"]
    assert any(c["label"] == "Recursion" for c in unpractised)


def test_the_queue_is_ordered_most_at_risk_first(client, auth_headers, studied):
    body = client.get("/api/review/next", headers=auth_headers).json()

    probabilities = [c["p_correct"] for c in body["concepts"]]
    assert probabilities == sorted(probabilities)


def test_limit_bounds_the_queue(client, auth_headers, studied):
    body = client.get("/api/review/next?limit=1", headers=auth_headers).json()

    assert body["count"] == 1
    assert len(body["concepts"]) == 1


def test_limit_is_validated(client, auth_headers):
    assert client.get("/api/review/next?limit=0", headers=auth_headers).status_code == 422
    assert client.get("/api/review/next?limit=999", headers=auth_headers).status_code == 422


# --- as_of ------------------------------------------------------------------

def test_a_future_as_of_lowers_recall(client, auth_headers, studied):
    """The exam-readiness hook: projecting forward must decay recall.

    Not a decorative parameter — the forgetting curve is the whole premise, so
    a date further out has to produce a lower P(correct) for a concept that has
    actually been practised.
    """
    now = datetime.now(timezone.utc)
    later = now + timedelta(days=60)

    def queue(at):
        # params=, not an f-string: the "+" in a "+00:00" offset is a literal
        # space once URL-decoded, so a hand-built query string is rejected.
        resp = client.get(
            "/api/review/next",
            params={"as_of": at.isoformat()},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["concepts"]

    today = {c["concept_id"]: c for c in queue(now)}
    future = {c["concept_id"]: c for c in queue(later)}

    practised = [cid for cid, c in today.items() if c["interaction_count"] > 0]
    assert practised, "fixture should have produced at least one practised concept"

    for cid in practised:
        assert future[cid]["p_correct"] <= today[cid]["p_correct"]


def test_a_z_suffixed_as_of_is_accepted(client, auth_headers, studied):
    """The offset form that survives a query string without encoding.

    "+00:00" decodes to a space and is rejected, so "Z" is the form a caller
    building a URL by hand should reach for.
    """
    resp = client.get(
        "/api/review/next?as_of=2027-01-01T00:00:00Z", headers=auth_headers
    )

    assert resp.status_code == 200


def test_a_naive_as_of_is_accepted(client, auth_headers, studied):
    """A timestamp with no offset must not blow up the elapsed-time arithmetic.

    Rows are stored naive and the ranking subtracts them from `as_of`; mixing a
    naive and an aware datetime raises TypeError, which would have been a 500 on
    a perfectly reasonable query string.
    """
    resp = client.get("/api/review/next?as_of=2027-01-01T00:00:00", headers=auth_headers)

    assert resp.status_code == 200


# --- isolation and degradation ---------------------------------------------

def test_one_users_queue_never_contains_anothers_concepts(client, minimal_pdf):
    a = register_and_verify(client, "queue-a@example.com", name="A")
    doc = upload_doc(client, a, minimal_pdf)
    a_ids = {
        c["concept_id"]
        for c in client.get("/api/review/next", headers=a).json()["concepts"]
    }
    assert a_ids

    b = register_and_verify(client, "queue-b@example.com", name="B")
    b_body = client.get("/api/review/next", headers=b).json()

    assert b_body["count"] == 0
    assert not a_ids & {c["concept_id"] for c in b_body["concepts"]}


def test_a_model_failure_degrades_instead_of_500ing(client, auth_headers, studied, monkeypatch):
    """A ranking is a nice-to-have on top of a study app.

    If the model cannot load or the forward pass raises, the user should still
    get a queue — in a worse order, marked as such — rather than a broken page.
    """
    from backend import review as review_module

    def boom():
        raise RuntimeError("checkpoint is corrupt")

    monkeypatch.setattr(review_module, "get_ranker", boom)

    resp = client.get("/api/review/next", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] > 0
    # Marked honestly: the order is least-practised-first, not an estimate.
    assert all(c["source"] == "unavailable" for c in body["concepts"])
    assert all(c["p_correct"] is None for c in body["concepts"])
    assert body["model_available"] is False


def test_model_available_reports_that_no_checkpoint_is_loaded(client, auth_headers, studied):
    """Honest about the fact that nothing is trained on Marigold's data yet."""
    body = client.get("/api/review/next", headers=auth_headers).json()

    assert body["model_available"] is False
    assert all(c["source"] == "prior" for c in body["concepts"])


def test_the_queue_requires_a_verified_account(client):
    from conftest import register_user

    resp = register_user(client, email="queue-gate@example.com", name="G")
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    client.cookies.clear()

    assert client.get("/api/review/next", headers=headers).status_code == 403
