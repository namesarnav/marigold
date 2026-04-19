import json
import random
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..concepts import assign_concepts, log_interaction, resolve_concept_for_card
from ..database import get_db
from ..dependencies import get_verified_user
from ..gemini import generate_flashcards
from ..models import Document, Flashcard, User, UserStats
from ..schemas import (
    FlashcardCreate,
    FlashcardOut,
    FlashcardPatch,
    StudyReviewRequest,
    StudyReviewResponse,
)

router = APIRouter(prefix="/api/flashcards", tags=["flashcards"])


def _bump_stat(user_id: int, field: str, amount: int, db: Session):
    today = date.today()
    stat = db.query(UserStats).filter(
        UserStats.user_id == user_id, UserStats.date == today
    ).first()
    if not stat:
        stat = UserStats(user_id=user_id, date=today)
        db.add(stat)
        db.flush()
    setattr(stat, field, getattr(stat, field) + amount)
    db.commit()


def _card_to_out(card: Flashcard) -> FlashcardOut:
    distractors = json.loads(card.distractors) if card.distractors else []
    options = [card.answer] + distractors
    random.shuffle(options)
    return FlashcardOut(
        id=card.id,
        question=card.question,
        answer=card.answer,
        topic=card.topic,
        options=options,
    )


def _get_doc_for_user(doc_id: int, user_id: int, db: Session) -> Document:
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{doc_id}", response_model=List[FlashcardOut])
def get_flashcards(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    _get_doc_for_user(doc_id, current_user.id, db)
    cards = (
        db.query(Flashcard)
        .filter(Flashcard.doc_id == doc_id)
        .order_by(Flashcard.id.asc())
        .all()
    )
    if not cards:
        raise HTTPException(status_code=404, detail="No flashcards found for this document.")
    _bump_stat(current_user.id, "flashcards_reviewed", len(cards), db)
    return [_card_to_out(c) for c in cards]


@router.post("/{doc_id}/regenerate", response_model=List[FlashcardOut])
async def regenerate_flashcards(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    doc = _get_doc_for_user(doc_id, current_user.id, db)
    if doc.status == "processing":
        raise HTTPException(status_code=400, detail="Document is still processing.")
    if not doc.extracted_text:
        raise HTTPException(status_code=400, detail="No stored text for this document. Re-upload the PDF.")

    db.query(Flashcard).filter(Flashcard.doc_id == doc_id).delete()
    doc.status = "processing"
    db.commit()

    try:
        flashcard_data = await generate_flashcards(doc.extracted_text, n=15)
    except Exception as e:
        doc.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to generate flashcards: {e}")

    new_cards = []
    for item in flashcard_data:
        distractors = item.get("distractors") or []
        card = Flashcard(
            doc_id=doc.id,
            question=item.get("question", "").strip(),
            answer=item.get("answer", "").strip(),
            topic=(item.get("topic") or "").strip() or None,
            distractors=json.dumps(distractors[:3]),
        )
        db.add(card)
        new_cards.append(card)

    db.flush()
    assign_concepts(db, new_cards, current_user.id)

    doc.status = "ready"
    db.commit()
    for c in new_cards:
        db.refresh(c)
    return [_card_to_out(c) for c in new_cards]


@router.post("/{doc_id}/new", response_model=FlashcardOut)
def create_flashcard(
    doc_id: int,
    payload: FlashcardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    _get_doc_for_user(doc_id, current_user.id, db)
    card = Flashcard(
        doc_id=doc_id,
        question=payload.question.strip(),
        answer=payload.answer.strip(),
        topic=payload.topic.strip() if payload.topic else None,
        distractors=json.dumps([]),
    )
    db.add(card)
    db.flush()
    resolve_concept_for_card(db, card, current_user.id)
    db.commit()
    db.refresh(card)
    return _card_to_out(card)


@router.patch("/{card_id}", response_model=FlashcardOut)
def patch_flashcard(
    card_id: int,
    payload: FlashcardPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    card = db.query(Flashcard).filter(Flashcard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Flashcard not found")
    _get_doc_for_user(card.doc_id, current_user.id, db)

    if payload.question is not None:
        card.question = payload.question
    if payload.answer is not None:
        card.answer = payload.answer
    if payload.topic is not None and payload.topic != card.topic:
        card.topic = payload.topic
        # The topic *is* the concept key until embeddings land, so an edited
        # topic must re-resolve. Past interactions keep pointing at the old
        # concept, which is correct: they happened under the old grouping.
        card.concept_id = None
        resolve_concept_for_card(db, card, current_user.id)
    db.commit()
    db.refresh(card)
    return _card_to_out(card)


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flashcard(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    card = db.query(Flashcard).filter(Flashcard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Flashcard not found")
    _get_doc_for_user(card.doc_id, current_user.id, db)
    db.delete(card)
    db.commit()


@router.post("/{card_id}/review", response_model=StudyReviewResponse)
def review_flashcard(
    card_id: int,
    payload: StudyReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Record a study-mode self-grade.

    Study mode previously tracked "known" purely in React state, so every
    self-graded review was thrown away on unmount. Those are the cheapest
    retention signals the app produces, so they now land in the interaction log
    alongside quiz answers — distinguished by `source="study"`, since a
    self-grade is weaker evidence than a scored multiple-choice answer and the
    model should be free to weight it differently.
    """
    card = db.query(Flashcard).filter(Flashcard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Flashcard not found")
    _get_doc_for_user(card.doc_id, current_user.id, db)

    interaction = log_interaction(
        db,
        user_id=current_user.id,
        card=card,
        source="study",
        correct=payload.known,
        response_time_ms=payload.response_time_ms,
    )
    db.commit()
    return StudyReviewResponse(
        interaction_id=interaction.id,
        concept_id=interaction.concept_id,
    )
