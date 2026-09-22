"""Deterministic stand-ins for the Gemini API, so the suite never hits the network.

`fake_embed_api` replaces `backend.embeddings._call_embed_api` — the single
function there that makes a request — so batching, retries, count checks and
normalisation all still run for real in every test.

Its vectors are a hashed bag of words: texts sharing words point in similar
directions. That is crude, but it is enough for retrieval tests to assert that
the chunk about photosynthesis outranks the chunk about the French Revolution,
which a random vector could not do.
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Sequence

from backend.config import EMBEDDING_DIM

_PREFIX = re.compile(r"^(task: search result \| query: |title: [^|]* \| text: )")
_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = {"the", "a", "an", "of", "and", "is", "in", "to", "what", "how", "are", "does"}


def fake_vector(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    vector = [0.0] * dim
    body = _PREFIX.sub("", text).lower()
    for word in _WORD.findall(body):
        if word in _STOPWORDS:
            continue
        slot = int(hashlib.sha256(word.encode()).hexdigest(), 16) % dim
        vector[slot] += 1.0
    if not any(vector):
        vector[0] = 1.0  # never a zero vector
    return vector


def fake_embed_api(client, model: str, texts: Sequence[str], dim: int) -> List[List[float]]:
    return [fake_vector(t, dim) for t in texts]


_CHUNK_TAG = re.compile(r'<chunk id="(\d+)" pages="[^"]*">\n(.*?)\n</chunk>', re.S)
_TOPIC = re.compile(r'flashcards about the topic "([^"]+)"')
_TOPIC_COUNT = re.compile(r"Name exactly (\d+) distinct topics")
_CARD_COUNT = re.compile(r"Write up to (\d+) flashcards")


class FakeGemini:
    """Answers the two rag prompts the way a well-behaved model would.

    * Topic prompt: returns `topics` (truncated to the count asked for).
    * Card prompt: writes cards from the chunks it was shown, citing their real
      ids — or, for topics in `hallucinate`, citing an id it was never shown.

    Patched over `backend.gemini.generate_json`. Every prompt is kept in
    `prompts` so tests can assert on what the model was (and was not) shown.
    """

    def __init__(self, topics, hallucinate=(), cards_per_topic=None):
        self.topics = list(topics)
        self.hallucinate = set(hallucinate)
        self.cards_per_topic = cards_per_topic
        self.prompts = []

    async def __call__(self, prompt, label=""):
        self.prompts.append((label, prompt))
        if label == "rag:topics":
            n = int(_TOPIC_COUNT.search(prompt).group(1))
            return self.topics[:n]
        if label == "rag:cards":
            topic = _TOPIC.search(prompt).group(1)
            chunks = [(int(i), text) for i, text in _CHUNK_TAG.findall(prompt)]
            n = self.cards_per_topic or int(_CARD_COUNT.search(prompt).group(1))
            cards = []
            for k in range(n):
                chunk_id, text = chunks[k % len(chunks)]
                cited = [999_999] if topic in self.hallucinate else [chunk_id]
                cards.append({
                    "question": f"{topic}: question {k}?",
                    "answer": text.split(".")[0],
                    "topic": topic,
                    "distractors": ["w1", "w2", "w3"],
                    "source_chunk_ids": cited,
                })
            return cards
        raise AssertionError(f"unexpected Gemini call: {label}")
