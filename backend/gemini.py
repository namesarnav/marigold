import json
import time
from typing import Any, Dict, List

import anyio
from google.genai import types

from . import usage
from .config import get_settings
from .retry import with_retry


def _client():
    # Imported at call time so the test suite's network guard, which replaces
    # genai.Client, is always the one constructed.
    from google import genai

    return genai.Client(api_key=get_settings().gemini_api_key)


def parse_json_response(text: str) -> Any:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned)


def _token_count(meta, name: str):
    value = getattr(meta, name, None) if meta is not None else None
    return int(value) if value is not None else None


async def generate_json(prompt: str, label: str = "") -> Any:
    """One Gemini call that must answer in JSON. Retried on transient errors.

    JSON output mode is requested, and the markdown-fence stripping is kept as
    a fallback for any response that wraps the JSON anyway. Usage metadata from
    the response is recorded into the active usage tracker, if any.
    """
    settings = get_settings()
    client = _client()
    model = settings.gemini_model

    def _call():
        # google-genai uses sync I/O; run in a thread so FastAPI handlers can
        # stay async.
        return with_retry(
            lambda: client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            ),
            what="Generation request",
        )

    started = time.perf_counter()
    response = await anyio.to_thread.run_sync(_call)
    meta = getattr(response, "usage_metadata", None)
    usage.record(usage.CallRecord(
        kind="generate",
        model=model,
        latency_seconds=time.perf_counter() - started,
        prompt_tokens=_token_count(meta, "prompt_token_count"),
        output_tokens=_token_count(meta, "candidates_token_count"),
        thinking_tokens=_token_count(meta, "thoughts_token_count"),
        label=label,
    ))
    return parse_json_response(response.text)


async def generate_flashcards(extracted_text: str, n: int = 15) -> List[Dict[str, Any]]:
    """The full-document path: every card from one call over the whole text."""
    prompt = f"""
You are a study assistant. Extract flashcards from the following text.
Return ONLY a JSON array, no markdown, no explanation. Format:
[
  {{
    "question": "...",
    "answer": "...",
    "topic": "...",
    "distractors": ["wrong1", "wrong2", "wrong3"]
  }}
]

Generate exactly {n} flashcards. Cover the most important concepts.
Text: {extracted_text}
"""
    return await generate_json(prompt, label="full:cards")
