"""Read access to the interaction log and the user's concept map.

These are the endpoints the ml/ service reads from: the knowledge-tracing
forward pass needs a user's ordered interaction sequence, and the scheduler
needs to know which concepts exist to rank them. Nothing here writes — writes
go through `backend.concepts.log_interaction` at the point the attempt happens.
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..concepts import interaction_sequence
from ..database import get_db
from ..dependencies import get_verified_user
from ..models import Concept, Flashcard, Interaction, User
from ..schemas import ConceptOut, InteractionOut, InteractionSequenceOut

router = APIRouter(prefix="/api", tags=["interactions"])

# Caps the response so a long-lived account cannot be asked for its entire
# history in one request. SAKT-style models use a bounded attention window
# anyway, so the most recent slice is what actually gets consumed.
MAX_SEQUENCE_LIMIT = 2000


@router.get("/interactions/me", response_model=InteractionSequenceOut)
def my_interactions(
    limit: int = Query(default=500, ge=1, le=MAX_SEQUENCE_LIMIT),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    rows = interaction_sequence(db, current_user.id, limit=limit)
    return InteractionSequenceOut(
        user_id=current_user.id,
        count=len(rows),
        interactions=[
            InteractionOut(
                id=r.id,
                concept_id=r.concept_id,
                flashcard_id=r.flashcard_id,
                source=r.source,
                correct=r.correct,
                response_time_ms=r.response_time_ms,
                responded_at=r.responded_at.isoformat(),
            )
            for r in rows
        ],
    )


@router.get("/concepts/me", response_model=List[ConceptOut])
def my_concepts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """The user's concepts with how much evidence each one has.

    `interaction_count` is the number that decides cold start: a concept with
    few attempts should be scored by the Bayesian prior rather than the sequence
    model, so it is surfaced here rather than recomputed by every consumer.
    """
    card_counts = dict(
        db.query(Flashcard.concept_id, func.count(Flashcard.id))
        .filter(Flashcard.concept_id.isnot(None))
        .group_by(Flashcard.concept_id)
        .all()
    )
    interaction_counts = dict(
        db.query(Interaction.concept_id, func.count(Interaction.id))
        .filter(Interaction.user_id == current_user.id)
        .group_by(Interaction.concept_id)
        .all()
    )

    concepts = (
        db.query(Concept)
        .filter(Concept.user_id == current_user.id)
        .order_by(Concept.label.asc())
        .all()
    )
    return [
        ConceptOut(
            id=c.id,
            key=c.key,
            label=c.label,
            source=c.source,
            card_count=card_counts.get(c.id, 0),
            interaction_count=interaction_counts.get(c.id, 0),
        )
        for c in concepts
    ]
