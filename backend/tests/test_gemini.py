"""The Gemini generation wrapper: JSON mode, retries, and usage accounting."""

import asyncio

import pytest
from google.genai import types

from backend import gemini, retry
from backend.usage import track_usage
from test_embeddings import _api_error


class _FakeClient:
    def __init__(self, text, failures=()):
        self.failures = list(failures)
        self.calls = []
        outer = self

        class _Models:
            def generate_content(self, model, contents, config):
                outer.calls.append((model, contents, config))
                if outer.failures:
                    raise outer.failures.pop(0)
                return types.GenerateContentResponse(
                    candidates=[types.Candidate(content=types.Content(
                        role="model", parts=[types.Part(text=text)]))],
                    usage_metadata=types.GenerateContentResponseUsageMetadata(
                        prompt_token_count=120, candidates_token_count=30,
                        thoughts_token_count=7,
                    ),
                )

        self.models = _Models()


@pytest.fixture()
def no_sleep(monkeypatch):
    monkeypatch.setattr(retry.time, "sleep", lambda s: None)


def test_requests_json_and_records_the_apis_own_token_counts(monkeypatch):
    client = _FakeClient('["a", "b"]')
    monkeypatch.setattr(gemini, "_client", lambda: client)

    with track_usage() as tracker:
        out = asyncio.run(gemini.generate_json("prompt", label="rag:topics"))

    assert out == ["a", "b"]
    _, _, config = client.calls[0]
    assert config.response_mime_type == "application/json"
    [rec] = tracker.calls
    assert (rec.kind, rec.label) == ("generate", "rag:topics")
    assert (rec.prompt_tokens, rec.output_tokens, rec.thinking_tokens) == (120, 30, 7)
    assert rec.estimated_input_tokens is None
    assert rec.latency_seconds >= 0


def test_retries_a_rate_limit(monkeypatch, no_sleep):
    client = _FakeClient("[]", failures=[_api_error(429), _api_error(503)])
    monkeypatch.setattr(gemini, "_client", lambda: client)
    assert asyncio.run(gemini.generate_json("p")) == []
    assert len(client.calls) == 3


def test_does_not_retry_a_bad_request(monkeypatch, no_sleep):
    client = _FakeClient("[]", failures=[_api_error(400)])
    monkeypatch.setattr(gemini, "_client", lambda: client)
    with pytest.raises(Exception):
        asyncio.run(gemini.generate_json("p"))
    assert len(client.calls) == 1


def test_fenced_json_is_still_parsed():
    assert gemini.parse_json_response('```json\n[1, 2]\n```') == [1, 2]


def test_recording_outside_a_tracker_is_a_no_op(monkeypatch):
    monkeypatch.setattr(gemini, "_client", lambda: _FakeClient("{}"))
    assert asyncio.run(gemini.generate_json("p")) == {}
