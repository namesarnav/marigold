import json
import random
from datetime import date, datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Document, Flashcard, QuizAnswer, QuizSession, User, UserStats
from ..schemas import (
    QuizAnswerRequest,
    QuizHistoryItem,
    QuizQuestion,
    QuizResults,
    QuizSkipRequest,
    QuizStartRequest,
    QuizStartResponse,
)

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


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


def _build_question(card: Flashcard, number: int, total: int) -> QuizQuestion:
    distractors = json.loads(card.distractors) if card.distractors else []
    options = [card.answer] + distractors
    random.shuffle(options)
    return QuizQuestion(
        question_id=card.id,
        text=card.question,
        options=options,
        question_number=number,
        total_questions=total,
    )


def _select_cards(doc_id: int, num_questions: int, db: Session) -> List[Flashcard]:
    cards = (
        db.query(Flashcard)
        .filter(Flashcard.doc_id == doc_id)
        .order_by(Flashcard.id.asc())
        .all()
    )
    if not cards:
        raise HTTPException(status_code=404, detail="No flashcards for this document.")
    return cards[:min(num_questions, len(cards))]


@router.post("/start", response_model=QuizStartResponse)
def start_quiz(
    payload: QuizStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(
        Document.id == payload.doc_id, Document.user_id == current_user.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    cards = _select_cards(payload.doc_id, payload.num_questions, db)
    session = QuizSession(
        user_id=current_user.id,
        doc_id=payload.doc_id,
        total_questions=len(cards),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    question = _build_question(cards[0], 1, len(cards))
    return QuizStartResponse(quiz_id=session.id, question=question)


def _get_session(quiz_id: int, user_id: int, db: Session) -> QuizSession:
    session = db.query(QuizSession).filter(
        QuizSession.id == quiz_id, QuizSession.user_id == user_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Quiz session not found")
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="Quiz already completed")
    return session


def _next_or_complete(session: QuizSession, db: Session):
    answered_ids = {a.flashcard_id for a in session.answers}
    all_cards = (
        db.query(Flashcard)
        .filter(Flashcard.doc_id == session.doc_id)
        .order_by(Flashcard.id.asc())
        .all()
    )
    selected = all_cards[:session.total_questions]
    remaining = [c for c in selected if c.id not in answered_ids]

    if not remaining:
        correct = sum(1 for a in session.answers if a.is_correct == 1)
        session.completed_at = datetime.utcnow()
        session.score = correct
        session.status = "completed"
        db.commit()
        _bump_stat(session.user_id, "quizzes_taken", 1, db)
        return {"completed": True, "quiz_id": session.id}

    number = len(answered_ids) + 1
    question = _build_question(remaining[0], number, session.total_questions)
    return {"completed": False, "quiz_id": session.id, "question": question.model_dump()}


@router.post("/{quiz_id}/answer")
def submit_answer(
    quiz_id: int,
    payload: QuizAnswerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _get_session(quiz_id, current_user.id, db)
    answered_ids = {a.flashcard_id for a in session.answers}
    all_cards = (
        db.query(Flashcard)
        .filter(Flashcard.doc_id == session.doc_id)
        .order_by(Flashcard.id.asc())
        .all()
    )
    selected = all_cards[:session.total_questions]
    remaining = [c for c in selected if c.id not in answered_ids]
    if not remaining:
        raise HTTPException(status_code=400, detail="All questions already answered")

    card = remaining[0]
    is_correct = 1 if payload.answer == card.answer else 0
    db.add(QuizAnswer(
        session_id=session.id,
        flashcard_id=card.id,
        user_answer=payload.answer,
        is_correct=is_correct,
        time_taken_seconds=payload.time_taken_seconds,
    ))
    db.commit()
    return _next_or_complete(session, db)


@router.post("/{quiz_id}/skip")
def skip_question(
    quiz_id: int,
    payload: QuizSkipRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _get_session(quiz_id, current_user.id, db)
    answered_ids = {a.flashcard_id for a in session.answers}
    all_cards = (
        db.query(Flashcard)
        .filter(Flashcard.doc_id == session.doc_id)
        .order_by(Flashcard.id.asc())
        .all()
    )
    selected = all_cards[:session.total_questions]
    remaining = [c for c in selected if c.id not in answered_ids]
    if not remaining:
        raise HTTPException(status_code=400, detail="All questions already answered")

    card = remaining[0]
    db.add(QuizAnswer(
        session_id=session.id,
        flashcard_id=card.id,
        user_answer=None,
        is_correct=None,
        time_taken_seconds=payload.time_taken_seconds,
    ))
    db.commit()
    return _next_or_complete(session, db)


@router.get("/history", response_model=List[QuizHistoryItem])
def quiz_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = (
        db.query(QuizSession)
        .filter(QuizSession.user_id == current_user.id, QuizSession.status == "completed")
        .order_by(QuizSession.completed_at.desc())
        .limit(20)
        .all()
    )
    result = []
    for s in sessions:
        total = s.total_questions or 0
        score = s.score or 0
        result.append(QuizHistoryItem(
            quiz_id=s.id,
            doc_filename=s.document.filename,
            score=score,
            total=total,
            percentage=(score / total * 100) if total else 0,
            completed_at=s.completed_at.isoformat() if s.completed_at else None,
        ))
    return result


@router.get("/{quiz_id}/results", response_model=QuizResults)
def get_results(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(QuizSession).filter(
        QuizSession.id == quiz_id, QuizSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Quiz session not found")

    answers = session.answers
    if not answers:
        raise HTTPException(status_code=400, detail="No answers recorded for this quiz.")

    correct = sum(1 for a in answers if a.is_correct == 1)
    total = len(answers)
    percentage = (correct / total * 100) if total else 0
    time_taken = sum(a.time_taken_seconds or 0 for a in answers)

    wrong_answers = [
        {
            "question": a.flashcard.question,
            "your_answer": a.user_answer,
            "correct_answer": a.flashcard.answer,
        }
        for a in answers
        if a.is_correct != 1
    ]

    return QuizResults(
        score=correct,
        total=total,
        percentage=percentage,
        time_taken_seconds=time_taken,
        wrong_answers=wrong_answers,
    )


@router.get("/{quiz_id}/review")
def get_review(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(QuizSession).filter(
        QuizSession.id == quiz_id, QuizSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Quiz session not found")

    questions = []
    for a in session.answers:
        card = a.flashcard
        distractors = json.loads(card.distractors) if card.distractors else []
        options = sorted([card.answer] + distractors)
        questions.append({
            "question": card.question,
            "options": options,
            "correct_answer": card.answer,
            "user_answer": a.user_answer,
            "is_correct": a.is_correct == 1 if a.is_correct is not None else None,
            "time_taken_seconds": a.time_taken_seconds,
        })

    return {"questions": questions}
