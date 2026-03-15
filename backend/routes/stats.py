from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import QuizSession, User, UserStats
from ..schemas import StatsResponse

router = APIRouter(prefix="/api/stats", tags=["stats"])


def calculate_streak(user_id: int, db: Session) -> int:
    rows = db.query(UserStats.date).filter(UserStats.user_id == user_id).all()
    dates = {r.date for r in rows}
    if not dates:
        return 0
    today = date.today()
    yesterday = today - timedelta(days=1)
    start = today if today in dates else yesterday
    if start not in dates:
        return 0
    streak = 0
    current = start
    while current in dates:
        streak += 1
        current -= timedelta(days=1)
    return streak


@router.get("/me", response_model=StatsResponse)
def get_my_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    all_stats = db.query(UserStats).filter(UserStats.user_id == current_user.id).all()
    total_quizzes = sum(s.quizzes_taken for s in all_stats)
    total_cards = sum(s.flashcards_reviewed for s in all_stats)

    completed = (
        db.query(QuizSession)
        .filter(QuizSession.user_id == current_user.id, QuizSession.status == "completed")
        .all()
    )
    avg_score = 0
    if completed:
        pcts = [
            (s.score / s.total_questions * 100)
            for s in completed
            if s.total_questions and s.score is not None
        ]
        avg_score = round(sum(pcts) / len(pcts)) if pcts else 0

    return StatsResponse(
        streak=calculate_streak(current_user.id, db),
        total_quizzes=total_quizzes,
        average_score=avg_score,
        total_flashcards_reviewed=total_cards,
    )
