"""Card generation: the full-document path, the retrieval path, and saving.

GENERATION_MODE picks the path; upload and regenerate both come through
`draft_cards`, so the switch means the same thing everywhere.

**full** — one Gemini call over the document's whole text (gemini.py). Cards
carry no citations.

**rag** — three steps:

1. *Topics.* Gemini reads an evenly spaced sample of the document's chunks and
   names RAG_TOPIC_COUNT distinct topics. Sampled rather than reading the whole
   text, because sending everything is exactly the cost this path exists to
   avoid; spread evenly so the back half of a long document is represented.
   (A PDF outline would be a better hint where one exists, but the PDF bytes
   are not kept after upload, so regenerate could not use it and the two
   entry points would pick topics differently.)
2. *Retrieve.* Each topic is embedded as a query and its RAG_TOP_K nearest
   chunks are retrieved from this document only (retrieval.py).
3. *Generate.* For each topic, Gemini writes cards from only those chunks and
   returns the chunk ids each card relies on. A card citing any id outside its
   retrieved set — or citing nothing — is dropped, not repaired: an invented
   id means the model was not grounded in what it was shown, and the card's
   content cannot be trusted any more than its citation.

Cards are spread round-robin across topics, deduplicated by question, and
capped at CARDS_PER_UPLOAD. Each topic is asked for one card more than its
share, so a few rejections do not leave the deck short.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from . import gemini
from .config import get_settings
from .embeddings import aembed_query, embed_document_chunks
from .models import Document, DocumentChunk, Flashcard, FlashcardSource
from .retrieval import RetrievedChunk, retrieve_chunks

logger = logging.getLogger(__name__)

# Budget for the topic-discovery sample, in estimated tokens. Enough to see a
# document's shape; small next to sending the whole thing.
TOPIC_SAMPLE_TOKENS = 12_000
# Topic calls run concurrently, but bounded: Gemini rate limits per minute, and
# backoff (retry.py) is the fallback, not the plan.
MAX_CONCURRENT_TOPIC_CALLS = 3


@dataclass
class CardDraft:
    question: str
    answer: str
    topic: Optional[str]
    distractors: List[str]
    chunk_ids: List[int] = field(default_factory=list)


@dataclass
class DraftResult:
    cards: List[CardDraft]
    mode: str  # the mode that actually ran: "full" or "rag"
    # Diagnostics for logs and the eval script.
    topics: List[str] = field(default_factory=list)
    retrieved: Dict[str, List[int]] = field(default_factory=dict)  # topic -> chunk ids
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    fallback_reason: Optional[str] = None


class GenerationError(RuntimeError):
    pass


# --- shared ------------------------------------------------------------------


def _clean_card(item: Dict[str, Any]) -> Optional[CardDraft]:
    if not isinstance(item, dict):
        return None
    question = str(item.get("question") or "").strip()
    answer = str(item.get("answer") or "").strip()
    if not question or not answer:
        return None
    distractors = [str(d) for d in (item.get("distractors") or []) if str(d).strip()]
    return CardDraft(
        question=question,
        answer=answer,
        topic=(str(item.get("topic") or "").strip() or None),
        distractors=distractors[:3],
    )


def _question_key(question: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()


# --- full --------------------------------------------------------------------


async def draft_full(
    document: Document, n: int, full_generator: Callable[..., Awaitable[List[Dict]]]
) -> DraftResult:
    if not document.extracted_text:
        raise GenerationError("No stored text for this document. Re-upload the PDF.")
    items = await full_generator(document.extracted_text, n=n)
    cards = [c for c in (_clean_card(i) for i in items or []) if c is not None]
    return DraftResult(cards=cards, mode="full")


# --- rag ---------------------------------------------------------------------


def sample_chunks(chunks: Sequence[DocumentChunk], budget_tokens: int) -> List[DocumentChunk]:
    """Evenly spaced chunks whose total estimated size fits the budget."""
    if not chunks:
        return []
    total = sum(c.token_count for c in chunks)
    if total <= budget_tokens:
        return list(chunks)
    average = max(1, total // len(chunks))
    count = max(1, min(len(chunks), budget_tokens // average))
    step = len(chunks) / count
    picked = [chunks[int(i * step)] for i in range(count)]
    # Overlapping neighbours waste budget; the stride already avoids most.
    return list(dict.fromkeys(picked))


def _topics_prompt(sample: Sequence[DocumentChunk], n: int) -> str:
    excerpts = "\n\n".join(
        f"[pages {c.page_start}-{c.page_end}]\n{c.text}" for c in sample
    )
    return f"""
You are planning flashcards for a study document. Below are excerpts sampled
evenly from across the document.

Name exactly {n} distinct topics that together cover the document's most
important material. Each topic is a short noun phrase (2 to 8 words) specific
enough to search the document for, e.g. "light-dependent reactions" rather
than "biology". Do not repeat or overlap topics.

Return ONLY a JSON array of {n} strings.

Excerpts:
{excerpts}
"""


def _cards_prompt(topic: str, retrieved: Sequence[RetrievedChunk], n: int) -> str:
    sources = "\n\n".join(
        f'<chunk id="{r.chunk.id}" pages="{r.chunk.page_start}-{r.chunk.page_end}">\n'
        f"{r.chunk.text}\n</chunk>"
        for r in retrieved
    )
    return f"""
You are a study assistant writing flashcards about the topic "{topic}".

Use ONLY the source chunks below. Every fact in a question or answer must be
stated in the chunks; do not use outside knowledge. If the chunks do not
support {n} good cards, write fewer.

For each card, list in "source_chunk_ids" the id of every chunk the answer
relies on. Use only ids that appear below.

Return ONLY a JSON array, no markdown. Format:
[
  {{
    "question": "...",
    "answer": "...",
    "topic": "{topic}",
    "distractors": ["wrong1", "wrong2", "wrong3"],
    "source_chunk_ids": [123]
  }}
]

Write up to {n} flashcards.

Source chunks:
{sources}
"""


def validate_citations(item: Dict[str, Any], allowed_ids: Sequence[int]) -> Optional[List[int]]:
    """The card's cited chunk ids, or None if the card must be rejected.

    Rejected when it cites nothing, cites anything that is not an integer id,
    or cites any id outside `allowed_ids` (the chunks it was shown).
    """
    raw = item.get("source_chunk_ids") if isinstance(item, dict) else None
    if not isinstance(raw, list) or not raw:
        return None
    allowed = set(allowed_ids)
    ids: List[int] = []
    for value in raw:
        if isinstance(value, bool):
            return None
        try:
            chunk_id = int(value)
        except (TypeError, ValueError):
            return None
        if isinstance(value, float) and value != chunk_id:
            return None
        if chunk_id not in allowed:
            return None
        if chunk_id not in ids:
            ids.append(chunk_id)
    return ids


async def _topics(sample: Sequence[DocumentChunk], n: int) -> List[str]:
    raw = await gemini.generate_json(_topics_prompt(sample, n), label="rag:topics")
    if not isinstance(raw, list):
        raise GenerationError("topic list was not a JSON array")
    seen = set()
    topics = []
    for value in raw:
        topic = str(value).strip() if isinstance(value, (str, int, float)) else ""
        key = _question_key(topic)
        if topic and key not in seen:
            seen.add(key)
            topics.append(topic)
    if not topics:
        raise GenerationError("Gemini returned no usable topics")
    return topics[:n]


async def draft_rag(db: Session, document: Document, n: int) -> DraftResult:
    settings = get_settings()

    await embed_document_chunks(db, document)
    chunks = [c for c in document.chunks if c.embedding is not None]
    if not chunks:
        raise GenerationError("document has no embedded chunks")

    topic_count = max(1, min(settings.rag_topic_count, n, len(chunks)))
    topics = await _topics(sample_chunks(chunks, TOPIC_SAMPLE_TOKENS), topic_count)

    # Retrieval touches the session, which is not safe to share across
    # concurrent tasks — so it runs first, sequentially. Only the Gemini calls
    # below run concurrently.
    retrieved: Dict[str, List[RetrievedChunk]] = {}
    for topic in topics:
        vector = await aembed_query(topic)
        retrieved[topic] = retrieve_chunks(db, document.id, vector, settings.rag_top_k)

    per_topic = math.ceil(n / len(topics)) + 1
    gate = asyncio.Semaphore(MAX_CONCURRENT_TOPIC_CALLS)

    async def cards_for(topic: str):
        async with gate:
            return await gemini.generate_json(
                _cards_prompt(topic, retrieved[topic], per_topic), label="rag:cards"
            )

    responses = await asyncio.gather(*(cards_for(t) for t in topics if retrieved[t]))

    result = DraftResult(
        cards=[], mode="rag", topics=topics,
        retrieved={t: [r.chunk.id for r in retrieved[t]] for t in topics},
    )
    per_topic_cards: List[List[CardDraft]] = []
    for topic, raw in zip([t for t in topics if retrieved[t]], responses):
        allowed = result.retrieved[topic]
        accepted: List[CardDraft] = []
        for item in raw if isinstance(raw, list) else []:
            card = _clean_card(item)
            ids = validate_citations(item, allowed)
            if card is None or ids is None:
                result.rejected.append({
                    "topic": topic,
                    "reason": "malformed card" if card is None else "invalid or missing citations",
                    "cited": item.get("source_chunk_ids") if isinstance(item, dict) else None,
                    "allowed": allowed,
                })
                continue
            card.chunk_ids = ids
            card.topic = card.topic or topic
            accepted.append(card)
        per_topic_cards.append(accepted)

    # Round-robin across topics so no one topic crowds out the rest.
    seen_questions = set()
    for depth in range(per_topic):
        for cards in per_topic_cards:
            if depth < len(cards) and len(result.cards) < n:
                key = _question_key(cards[depth].question)
                if key not in seen_questions:
                    seen_questions.add(key)
                    result.cards.append(cards[depth])

    if result.rejected:
        logger.warning(
            "Document %s: rejected %d generated card(s) for invalid citations",
            document.id, len(result.rejected),
        )
    if not result.cards:
        raise GenerationError("no cards survived citation validation")
    return result


# --- entry point ---------------------------------------------------------------


async def draft_cards(
    db: Session,
    document: Document,
    full_generator: Callable[..., Awaitable[List[Dict]]],
    mode: Optional[str] = None,
    n: Optional[int] = None,
) -> DraftResult:
    """Draft a document's cards in the configured mode. Writes nothing but
    chunk embeddings.

    `full_generator` is passed in rather than imported here so the routes stay
    the seam the existing tests patch (`backend.routes.*.generate_flashcards`).

    rag mode falls back to full for a document with no chunks: those were
    uploaded before chunking existed, and their pages were joined into one
    string without boundaries, so accurate page citations cannot be rebuilt.
    Re-uploading the PDF gives them chunks.
    """
    settings = get_settings()
    mode = mode or settings.generation_mode
    n = n or settings.cards_per_upload

    if mode == "rag":
        if not document.chunks:
            logger.warning(
                "Document %s has no chunks (uploaded before retrieval existed); "
                "generating with the full-document path instead", document.id,
            )
            result = await draft_full(document, n, full_generator)
            result.fallback_reason = "document has no chunks; re-upload for citations"
            return result
        return await draft_rag(db, document, n)
    return await draft_full(document, n, full_generator)


def save_cards(db: Session, document: Document, drafts: Sequence[CardDraft]) -> List[Flashcard]:
    """Insert drafted cards and their citations. Flushes, does not commit.

    Concepts are left to the caller (`concepts.assign_concepts`), which keeps
    concept resolution at the route, where it has always been called from.
    """
    cards = []
    for draft in drafts:
        card = Flashcard(
            doc_id=document.id,
            question=draft.question,
            answer=draft.answer,
            topic=draft.topic,
            distractors=json.dumps(draft.distractors[:3]),
        )
        db.add(card)
        cards.append(card)
    db.flush()
    for card, draft in zip(cards, drafts):
        for chunk_id in draft.chunk_ids:
            db.add(FlashcardSource(flashcard_id=card.id, chunk_id=chunk_id))
    db.flush()
    return cards


def delete_cards(db: Session, document_id: int) -> int:
    """Delete a document's cards one at a time through the ORM.

    Not a bulk `query(...).delete()`: that emits one raw DELETE and skips ORM
    cascades, so `Flashcard.quiz_answers` never ran and any card answered in a
    quiz tripped quiz_answers_flashcard_id_fkey. Citations go by database
    cascade; interactions are untouched (ON DELETE SET NULL), so attempt
    history survives its card.
    """
    cards = db.query(Flashcard).filter(Flashcard.doc_id == document_id).all()
    for card in cards:
        db.delete(card)
    db.flush()
    return len(cards)
