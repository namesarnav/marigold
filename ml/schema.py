"""The ML-facing view of the interaction and concept schema.

DB-agnostic SQLAlchemy models, so the pipeline can be prototyped against SQLite
and moved to Postgres without a rewrite.

## Important: this overlaps with `backend/models.py`

The backend **already has** `concepts` and `interactions` tables in production
use, and they do not match the shape specified for this pipeline. These models
are therefore written as the *target* schema, with the divergence recorded here
rather than silently creating a second, conflicting definition of the same
tables. Reconciling the two is a migration, and it needs a decision before
either side is treated as canonical.

| This module            | `backend/models.py`        | Status |
| ---------------------- | -------------------------- | ------ |
| `Concept.cluster_label`| `Concept.label`            | Rename |
| `Concept.embedding`    | `Concept.centroid` (Text)  | Same role; needs a real vector type |
| `Concept.source_card_ids` | implicit via `Flashcard.concept_id` | Denormalisation |
| `Interaction.card_id`  | `Interaction.flashcard_id` | Rename |
| `Interaction.timestamp`| `Interaction.responded_at` | Rename |
| — | `Concept.key`, `Concept.source` | Backend-only; drives topic-based fallback |
| — | `Interaction.source`, `quiz_session_id` | Backend-only; quiz vs. study provenance |

Two divergences are substantive rather than cosmetic:

1. **`correct` is nullable in the backend and non-nullable in the spec.** The
   backend is right and this module follows it. A skipped question is an event
   that happened but yields no evidence about recall; storing it as `False`
   teaches the model that running out of time means forgetting. Skips are
   filtered before they ever reach the model — see `_usable` in
   `ml/inference/predict.py` and `fit_concept_prior` in
   `ml/models/coldstart.py`.

2. **`source_card_ids` denormalises a relationship that already exists.** The
   backend derives a concept's cards from `flashcards.concept_id`. Storing the
   list on the concept as well means two sources of truth that can disagree.
   It is included here because the spec calls for it and it is genuinely
   convenient for the clustering job's output, but it should be treated as a
   derived cache, not authority.

## Postgres notes

`embedding` is `JSON` here so the models run on SQLite during prototyping. In
Postgres it should be `pgvector`'s `vector(384)` — 384 being all-MiniLM-L6-v2's
dimension — which allows an ivfflat/hnsw index and nearest-concept queries in
the database instead of in Python. That is a real migration (the pgvector
extension must be installed on the k3s Postgres), not a column type swap.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Separate declarative base from the backend's.

    Deliberate: importing `backend.database.Base` here would couple the ML
    service to the API's settings loading and its whole dependency tree, which
    defeats the point of containerising them separately.
    """


class Concept(Base):
    """A cluster of flashcards testing the same underlying idea."""

    __tablename__ = "concepts"

    id = Column(Integer, primary_key=True)

    # Human-readable name for the cluster. Display only — nothing keys off it.
    cluster_label = Column(String(255), nullable=False)

    # Cluster centroid in embedding space. JSON list of floats on SQLite;
    # vector(384) on Postgres with pgvector. Nullable because a concept can
    # exist before the clustering job has run over it.
    embedding = Column(JSON, nullable=True)

    # Denormalised member list. See the docstring: derived cache, not authority.
    source_card_ids = Column(JSON, nullable=False, default=list)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    interactions = relationship("Interaction", back_populates="concept")


class Interaction(Base):
    """One graded recall attempt. Append-only.

    This is the KT model's input row. It is an event log: rows are never updated
    after being written, because a prediction made last week was made against
    the history as it stood then, and rewriting history makes past predictions
    unreproducible.
    """

    __tablename__ = "interactions"
    __table_args__ = (
        # The per-user sequence the SAKT forward pass reads.
        Index("ix_ml_interactions_user_time", "user_id", "timestamp"),
        # A single concept's history, for its forgetting curve.
        Index("ix_ml_interactions_user_concept_time", "user_id", "concept_id", "timestamp"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    concept_id = Column(
        Integer, ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True
    )
    # SET NULL, not CASCADE: deleting a flashcard must not delete the evidence
    # that the user once answered it.
    card_id = Column(Integer, nullable=True)

    # Nullable — see divergence (1) in the module docstring. NULL means skipped.
    correct = Column(Boolean, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    concept = relationship("Concept", back_populates="interactions")
