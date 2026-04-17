"""Concept resolution and interaction logging.

Two responsibilities, kept in one place so every call site records history the
same way:

1. Map a flashcard to a `Concept`. Eventually this is the job of the embedding
   clustering pass in the ml/ service; until that exists we derive concepts from
   the Gemini-assigned `topic`, falling back to the document. The fallback is
   explicit and testable so swapping in embeddings later is a change to
   `resolve_concept_for_card` alone.

2. Append an `Interaction` row. Every graded recall attempt in the app — quiz
   answer, quiz skip, study-mode self-grade — must go through
   `log_interaction`, because the knowledge-tracing model is only as good as the
   completeness of this log.
"""

import re
from datetime import datetime
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Concept, Flashcard, Interaction

# Sources a concept key can be derived from, weakest last.
SOURCE_TOPIC = "topic"
SOURCE_DOCUMENT = "document"

_WHITESPACE = re.compile(r"\s+")
_STRIPPABLE = re.compile(r"^[^\w]+|[^\w]+$")


def normalize_concept_key(label: str) -> str:
    """Fold a human-written topic label into a stable dedupe key.

    "Photosynthesis ", "photosynthesis" and "Photosynthesis!" are the same
    concept; Gemini is not consistent about casing or trailing punctuation.
    Returns "" when nothing usable is left, which callers treat as "no topic".
    """
    if not label:
        return ""
    key = _WHITESPACE.sub(" ", label).strip().lower()
    key = _STRIPPABLE.sub("", key)
    return key


def get_or_create_concept(
    db: Session, user_id: int, key: str, label: str, source: str
) -> Concept:
    """Fetch the user's concept for `key`, creating it if absent.

    The insert runs in a savepoint so a concurrent request that created the same
    concept first costs us a requery rather than poisoning the caller's
    transaction.
    """
    existing = (
        db.query(Concept)
        .filter(Concept.user_id == user_id, Concept.key == key)
        .first()
    )
    if existing:
        return existing

    concept = Concept(user_id=user_id, key=key, label=label, source=source)
    try:
        with db.begin_nested():
            db.add(concept)
            db.flush()
    except IntegrityError:
        # Lost the race on uq_concept_user_key — the other writer's row is fine.
        return (
            db.query(Concept)
            .filter(Concept.user_id == user_id, Concept.key == key)
            .one()
        )
    return concept


def resolve_concept_for_card(db: Session, card: Flashcard, user_id: int) -> Concept:
    """Return the concept this card tests, assigning one if it has none.

    Preference order: the card's existing assignment, then its topic, then the
    document it came from. The document fallback keeps every interaction
    attributable to *something* — a concept with one document's worth of cards is
    still a usable retention signal, and it gets replaced when clustering runs.
    """
    if card.concept_id is not None:
        concept = db.query(Concept).filter(Concept.id == card.concept_id).first()
        if concept is not None:
            return concept

    topic_key = normalize_concept_key(card.topic or "")
    if topic_key:
        concept = get_or_create_concept(
            db, user_id, f"topic:{topic_key}", (card.topic or "").strip(), SOURCE_TOPIC
        )
    else:
        doc = card.document
        label = doc.filename if doc is not None else f"Document {card.doc_id}"
        concept = get_or_create_concept(
            db, user_id, f"document:{card.doc_id}", label, SOURCE_DOCUMENT
        )

    card.concept_id = concept.id
    return concept


def assign_concepts(db: Session, cards: List[Flashcard], user_id: int) -> None:
    """Resolve concepts for freshly generated cards.

    Called at card-creation time so `flashcards.concept_id` is populated up
    front; `resolve_concept_for_card` still runs lazily at log time to cover
    cards created before this existed or edited into a new topic.
    """
    for card in cards:
        resolve_concept_for_card(db, card, user_id)


def log_interaction(
    db: Session,
    *,
    user_id: int,
    card: Flashcard,
    source: str,
    correct: Optional[bool],
    response_time_ms: Optional[int] = None,
    quiz_session_id: Optional[int] = None,
    responded_at: Optional[datetime] = None,
) -> Interaction:
    """Append one recall attempt to the interaction log.

    Adds and flushes but does not commit: call sites fold this into the commit
    that persists the attempt itself, so an interaction can never be recorded
    for an answer that was rolled back.

    `correct=None` records a skip — the attempt happened but yielded no evidence
    about recall.
    """
    concept = resolve_concept_for_card(db, card, user_id)
    interaction = Interaction(
        user_id=user_id,
        concept_id=concept.id,
        flashcard_id=card.id,
        quiz_session_id=quiz_session_id,
        source=source,
        correct=correct,
        response_time_ms=response_time_ms,
        responded_at=responded_at or datetime.utcnow(),
    )
    db.add(interaction)
    db.flush()
    return interaction


def seconds_to_ms(seconds: Optional[float]) -> Optional[int]:
    """Convert the API's float seconds to the log's integer milliseconds.

    The quiz API has always spoken seconds; the KT model's feature is
    response_time_ms. Negative values are clamped to 0 — a client clock skew
    should not put impossible latencies into the training data.
    """
    if seconds is None:
        return None
    return max(0, int(round(seconds * 1000)))


def interaction_sequence(
    db: Session, user_id: int, limit: int = 1000
) -> List[Interaction]:
    """The user's most recent attempts, oldest first.

    Ordered ascending by time because that is the order a sequence model
    consumes; the limit selects the most *recent* window, so the query takes the
    newest `limit` rows and reverses them.
    """
    rows = (
        db.query(Interaction)
        .filter(Interaction.user_id == user_id)
        .order_by(Interaction.responded_at.desc(), Interaction.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))
