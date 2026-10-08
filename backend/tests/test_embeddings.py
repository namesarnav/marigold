"""Batching, retry and validation in backend/embeddings.py. No network."""

import math

import httpx
import pytest
from google.genai import errors as genai_errors
from google.genai import types

from backend import embeddings
from backend.config import EMBEDDING_DIM
from fakes import fake_embed_api, fake_vector

# The real request builder, captured at import — before the suite's autouse
# fixture swaps it for the fake.
_REAL_CALL_EMBED_API = embeddings._call_embed_api


def _api_error(code):
    cls = genai_errors.ClientError if code < 500 else genai_errors.ServerError
    return cls(code, {"error": {"code": code, "message": "x", "status": "X"}})


class _Recorder:
    """Records each request's batch; fails the first `failures` calls."""

    def __init__(self, failures=()):
        self.failures = list(failures)
        self.batches = []

    def __call__(self, client, model, texts, dim):
        self.batches.append(list(texts))
        if self.failures:
            raise self.failures.pop(0)
        return fake_embed_api(client, model, texts, dim)


@pytest.fixture()
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(embeddings, "_call_embed_api", rec)
    return rec


def _no_sleep(_):
    pass


def test_batches_requests_and_preserves_order(recorder):
    texts = [f"text number {i}" for i in range(7)]
    vectors = embeddings.embed_texts(texts, batch_size=3, sleep=_no_sleep)

    assert [len(b) for b in recorder.batches] == [3, 3, 1]
    assert len(vectors) == 7
    for text, vector in zip(texts, vectors):
        expected = fake_vector(text)
        norm = math.sqrt(sum(v * v for v in expected))
        assert vector == pytest.approx([v / norm for v in expected])


def test_vectors_are_unit_length(recorder):
    for vector in embeddings.embed_texts(["alpha beta beta gamma"], sleep=_no_sleep):
        assert math.sqrt(sum(v * v for v in vector)) == pytest.approx(1.0)


def test_document_and_query_prefixes(recorder):
    embeddings.embed_documents(["chunk text"], sleep=_no_sleep)
    embeddings.embed_query("what is it", sleep=_no_sleep)
    assert recorder.batches == [
        ["title: none | text: chunk text"],
        ["task: search result | query: what is it"],
    ]


@pytest.mark.parametrize("failure", [
    _api_error(429), _api_error(500), _api_error(503),
    httpx.ConnectError("reset"), httpx.ReadTimeout("slow"),
])
def test_retries_rate_limits_and_transient_errors(monkeypatch, failure):
    rec = _Recorder(failures=[failure, failure])
    monkeypatch.setattr(embeddings, "_call_embed_api", rec)
    slept = []
    vectors = embeddings.embed_texts(["x"], sleep=slept.append)
    assert len(vectors) == 1
    assert len(rec.batches) == 3
    assert len(slept) == 2
    assert all(0 <= s <= embeddings.MAX_DELAY_SECONDS for s in slept)


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_does_not_retry_requests_that_will_fail_again(monkeypatch, code):
    rec = _Recorder(failures=[_api_error(code)])
    monkeypatch.setattr(embeddings, "_call_embed_api", rec)
    with pytest.raises(genai_errors.APIError):
        embeddings.embed_texts(["x"], sleep=_no_sleep)
    assert len(rec.batches) == 1


def test_gives_up_after_max_attempts(monkeypatch):
    rec = _Recorder(failures=[_api_error(429)] * embeddings.MAX_ATTEMPTS)
    monkeypatch.setattr(embeddings, "_call_embed_api", rec)
    with pytest.raises(genai_errors.APIError):
        embeddings.embed_texts(["x"], sleep=_no_sleep)
    assert len(rec.batches) == embeddings.MAX_ATTEMPTS


def test_backoff_grows_and_is_capped():
    for attempt in range(10):
        cap = min(embeddings.MAX_DELAY_SECONDS, embeddings.BASE_DELAY_SECONDS * 2 ** attempt)
        assert 0 <= embeddings._backoff_delay(attempt) <= cap


def test_an_aggregated_response_is_rejected(monkeypatch):
    """One vector for several inputs is the list-of-strings mistake."""
    monkeypatch.setattr(
        embeddings, "_call_embed_api", lambda c, m, texts, d: [fake_vector(texts[0], d)]
    )
    with pytest.raises(embeddings.EmbeddingError, match="aggregated"):
        embeddings.embed_texts(["a", "b", "c"], sleep=_no_sleep)


def test_wrong_width_is_rejected(monkeypatch):
    monkeypatch.setattr(
        embeddings, "_call_embed_api", lambda c, m, texts, d: [[1.0] * (d * 4) for _ in texts]
    )
    with pytest.raises(embeddings.EmbeddingError, match=str(EMBEDDING_DIM)):
        embeddings.embed_texts(["a"], sleep=_no_sleep)


def test_api_call_wraps_each_text_in_its_own_content():
    """Guards the shape of the real request: separate Content per input."""

    class _Models:
        def embed_content(self, model, contents, config):
            self.args = (model, contents, config)
            return types.EmbedContentResponse(
                embeddings=[types.ContentEmbedding(values=[1.0, 0.0]) for _ in contents]
            )

    class _Client:
        models = _Models()

    client = _Client()
    out = _REAL_CALL_EMBED_API(client, "gemini-embedding-2", ["a", "b"], 2)

    model, contents, config = client.models.args
    assert model == "gemini-embedding-2"
    assert len(contents) == 2
    assert all(isinstance(c, types.Content) and len(c.parts) == 1 for c in contents)
    assert [c.parts[0].text for c in contents] == ["a", "b"]
    assert config.output_dimensionality == 2
    assert config.task_type is None  # rejected by gemini-embedding-2
    assert out == [[1.0, 0.0], [1.0, 0.0]]


def test_upload_embeds_every_chunk(client, auth_headers, minimal_pdf):
    from conftest import _TestSession, upload_doc

    from backend.models import DocumentChunk

    doc_id = upload_doc(client, auth_headers, minimal_pdf)
    db = _TestSession()
    try:
        rows = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).all()
    finally:
        db.close()
    assert rows
    assert all(r.embedding is not None and len(r.embedding) == EMBEDDING_DIM for r in rows)


def test_an_embedding_failure_does_not_fail_a_full_mode_upload(
    client, auth_headers, minimal_pdf, monkeypatch
):
    from conftest import _TestSession, upload_doc

    from backend.models import Document, DocumentChunk

    def boom(*args, **kwargs):
        raise _api_error(400)

    monkeypatch.setattr(embeddings, "_call_embed_api", boom)
    doc_id = upload_doc(client, auth_headers, minimal_pdf)

    db = _TestSession()
    try:
        assert db.get(Document, doc_id).status == "ready"
        rows = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).all()
        assert rows and all(r.embedding is None for r in rows)
    finally:
        db.close()


def test_usage_is_recorded_from_the_worker_thread(recorder):
    """aembed_* run the SDK call in a thread; the tracker must still see it."""
    import asyncio

    from backend.usage import track_usage

    with track_usage() as tracker:
        asyncio.run(embeddings.aembed_documents(["one two three", "four"]))
    [rec] = tracker.calls
    assert rec.kind == "embed"
    # No usage metadata on the Gemini embedding API: an estimate, kept apart.
    assert rec.prompt_tokens is None
    assert rec.estimated_input_tokens > 0
