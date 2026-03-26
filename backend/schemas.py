from typing import List, Optional
from pydantic import BaseModel, EmailStr

# Auth
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    id: int
    email: str
    name: str

    class Config:
        from_attributes = True


# Documents
class DocumentOut(BaseModel):
    id: int
    filename: str
    page_count: int
    status: str
    created_at: str

    class Config:
        from_attributes = True

class UploadResponse(BaseModel):
    doc_id: int

class DocumentPatch(BaseModel):
    filename: str


# Flashcards
class FlashcardOut(BaseModel):
    id: int
    question: str
    answer: str
    topic: Optional[str]
    options: List[str]

    class Config:
        from_attributes = True

class FlashcardPatch(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    topic: Optional[str] = None


class FlashcardCreate(BaseModel):
    question: str
    answer: str
    topic: Optional[str] = None


# Stats
class StatsResponse(BaseModel):
    streak: int
    total_quizzes: int
    average_score: int
    total_flashcards_reviewed: int

# Quiz
class QuizStartRequest(BaseModel):
    doc_id: int
    num_questions: int

class QuizQuestion(BaseModel):
    question_id: int
    text: str
    options: List[str]
    question_number: int
    total_questions: int
    time_limit_seconds: int = 30

class QuizStartResponse(BaseModel):
    quiz_id: int
    question: QuizQuestion


class QuizAnswerRequest(BaseModel):
    answer: str
    time_taken_seconds: float


class QuizSkipRequest(BaseModel):
    time_taken_seconds: float


class QuizResults(BaseModel):
    score: int
    total: int
    percentage: float
    time_taken_seconds: float
    wrong_answers: List[dict]


class QuizHistoryItem(BaseModel):
    quiz_id: int
    doc_filename: str
    score: int
    total: int
    percentage: float
    completed_at: Optional[str]
