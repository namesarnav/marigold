from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field

# Auth
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Issued on register/login, including to accounts that are not yet verified.

    An unverified account still needs a token: it is how the frontend reads
    `/me` and asks for a fresh verification email. The block on core features is
    enforced per-request by `get_verified_user`, not by withholding the token.
    `email_verified` is echoed here so the UI can show the interstitial without
    a second round trip.
    """

    access_token: str
    token_type: str = "bearer"
    email_verified: bool = True
    user: Optional["UserOut"] = None


class UserOut(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    email_verified: bool = False
    # Which sign-in methods this account has, e.g. ["password", "google"].
    # The UI uses it to decide whether "set a password" or "link an account"
    # makes sense to offer.
    auth_methods: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    message: str


class EmailOnlyRequest(BaseModel):
    """Shared by forgot-password and resend-verification.

    Both endpoints answer identically whether or not the address exists, so that
    neither can be used to enumerate accounts.
    """

    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class AuthProviderOut(BaseModel):
    provider: str
    created_at: Optional[str] = None


class OAuthProvidersResponse(BaseModel):
    """Which OAuth buttons the frontend should render.

    Driven by server config so a provider without credentials is not offered at
    all, rather than failing once the user clicks it.
    """

    providers: List[str]


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
    # Always "processing" at this point: the upload returns before generation
    # runs. Included so the client knows to start polling GET /api/documents/{id}
    # rather than assuming the cards are ready.
    status: str = "processing"

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


# Study reviews / interaction log
class StudyReviewRequest(BaseModel):
    known: bool
    response_time_ms: Optional[int] = Field(default=None, ge=0)


class StudyReviewResponse(BaseModel):
    interaction_id: int
    concept_id: Optional[int]


class ConceptOut(BaseModel):
    id: int
    key: str
    label: str
    source: str
    card_count: int
    interaction_count: int


class InteractionOut(BaseModel):
    """One element of the knowledge-tracing input sequence."""

    id: int
    concept_id: Optional[int]
    flashcard_id: Optional[int]
    source: str
    # None = skipped. Consumers must exclude these, not read them as incorrect.
    correct: Optional[bool]
    response_time_ms: Optional[int]
    responded_at: str


class InteractionSequenceOut(BaseModel):
    user_id: int
    count: int
    # Ascending by responded_at — the order a sequence model consumes.
    interactions: List[InteractionOut]


TokenResponse.model_rebuild()
