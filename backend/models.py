from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Float, Boolean, Date,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    """An account, which may be reachable through several auth methods at once.

    `password_hash` is nullable because an OAuth-only account never sets one, and
    `email_verified` gates access to every core feature (see
    `dependencies.get_verified_user`). Password signups start unverified;
    OAuth signups are created already verified, because the provider vouches for
    the address. The set of ways in to this account lives in `auth_providers`,
    not here — do not infer it from `password_hash` alone.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)
    email_verified = Column(Boolean, nullable=False, default=False)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    quiz_sessions = relationship("QuizSession", back_populates="user", cascade="all, delete-orphan")
    stats = relationship("UserStats", back_populates="user", cascade="all, delete-orphan")
    concepts = relationship("Concept", back_populates="user", cascade="all, delete-orphan")
    interactions = relationship("Interaction", back_populates="user", cascade="all, delete-orphan")
    auth_providers = relationship("AuthProvider", back_populates="user", cascade="all, delete-orphan")
    email_tokens = relationship("EmailToken", back_populates="user", cascade="all, delete-orphan")

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None


class AuthProvider(Base):
    """One way of signing in to a user account.

    A row per method, so an account can hold a password *and* Google *and*
    GitHub simultaneously. `provider_user_id` is the provider's stable subject
    id (Google `sub`, GitHub numeric `id`) and is NULL for the "password" row,
    which exists so that "how can this account be accessed?" is answerable from
    one table.

    The unique constraint on (provider, provider_user_id) is a hard stop against
    one provider identity being linked to two different local accounts, which is
    the shape an account-takeover bug would take.
    """

    __tablename__ = "auth_providers"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_provider_identity"),
        UniqueConstraint("user_id", "provider", name="uq_user_provider"),
    )

    PASSWORD = "password"
    GOOGLE = "google"
    GITHUB = "github"
    OAUTH_PROVIDERS = (GOOGLE, GITHUB)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String, nullable=False)  # google | github | password
    provider_user_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="auth_providers")


class EmailToken(Base):
    """Single-use record backing an emailed verification or reset link.

    The token handed to the user is itsdangerous-signed and carries its own
    expiry, but a signature alone cannot be revoked or spent. This table adds
    that: we store only the SHA-256 of the token (so a database leak does not
    yield usable links) and stamp `used_at` when it is redeemed. Both checks
    must pass, so a replayed link fails even though its signature is still valid.
    """

    __tablename__ = "email_tokens"
    __table_args__ = (
        Index("ix_email_tokens_user_purpose", "user_id", "purpose"),
    )

    VERIFY = "verify"
    RESET = "reset"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    purpose = Column(String, nullable=False)  # verify | reset
    token_hash = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="email_tokens")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)

    user = relationship("User", back_populates="refresh_tokens")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    page_count = Column(Integer, default=0)
    status = Column(String, default="processing")
    created_at = Column(DateTime, default=datetime.utcnow)
    extracted_text = Column(Text, nullable=True)

    user = relationship("User", back_populates="documents")
    flashcards = relationship("Flashcard", back_populates="document", cascade="all, delete-orphan")
    quiz_sessions = relationship("QuizSession", back_populates="document", cascade="all, delete-orphan")


class Flashcard(Base):
    __tablename__ = "flashcards"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    concept_id = Column(Integer, ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    topic = Column(String, nullable=True)
    distractors = Column(Text, nullable=True)  # JSON string

    document = relationship("Document", back_populates="flashcards")
    concept = relationship("Concept", back_populates="flashcards")
    quiz_answers = relationship("QuizAnswer", back_populates="flashcard", cascade="all, delete-orphan")
    # NOTE: deliberately no `interactions` relationship. Interaction history must
    # outlive the card it came from, so the FK is ON DELETE SET NULL and the ORM is
    # not given a cascade path from Flashcard to Interaction.


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    score = Column(Integer, nullable=True)
    total_questions = Column(Integer, nullable=True)
    status = Column(String, default="active")  # active | completed

    user = relationship("User", back_populates="quiz_sessions")
    document = relationship("Document", back_populates="quiz_sessions")
    answers = relationship("QuizAnswer", back_populates="session", cascade="all, delete-orphan")


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("quiz_sessions.id"), nullable=False)
    flashcard_id = Column(Integer, ForeignKey("flashcards.id"), nullable=False)
    user_answer = Column(Text, nullable=True)
    is_correct = Column(Integer, nullable=True)  # 1=correct, 0=wrong, null=skipped
    time_taken_seconds = Column(Float, nullable=True)

    session = relationship("QuizSession", back_populates="answers")
    flashcard = relationship("Flashcard", back_populates="quiz_answers")


class UserStats(Base):
    __tablename__ = "user_stats"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_date"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    quizzes_taken = Column(Integer, default=0)
    flashcards_reviewed = Column(Integer, default=0)

    user = relationship("User", back_populates="stats")


class Concept(Base):
    """A unit of knowledge the scheduler tracks retention for.

    Cards testing the same underlying idea share a concept, which is what lets
    forgetting generalize across documents instead of being tracked per card.
    Concepts are scoped to a user so their history spans all of their own
    documents. `key` is the stable dedupe handle; `centroid` is reserved for the
    embedding-clustering pass in the ml/ service and stays NULL until then.
    """

    __tablename__ = "concepts"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_concept_user_key"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String, nullable=False)
    label = Column(String, nullable=False)
    source = Column(String, nullable=False, default="topic")  # topic | document | embedding
    centroid = Column(Text, nullable=True)  # JSON array, set by the clustering pass
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="concepts")
    flashcards = relationship("Flashcard", back_populates="concept")
    interactions = relationship("Interaction", back_populates="concept")


class Interaction(Base):
    """Append-only log of one graded recall attempt.

    This is the input sequence for the knowledge-tracing model:
    (concept_id, correct, responded_at, response_time_ms) ordered per user.
    Rows are never updated or deleted except when the user's account goes away —
    treat this table as an event log, not mutable state.
    """

    __tablename__ = "interactions"
    __table_args__ = (
        # The per-user sequence read the KT forward pass needs.
        Index("ix_interactions_user_time", "user_id", "responded_at"),
        # Per-concept history, for the forgetting curve of a single concept.
        Index("ix_interactions_user_concept_time", "user_id", "concept_id", "responded_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    concept_id = Column(Integer, ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True)
    # Provenance. Both are nullable and ON DELETE SET NULL: deleting a card or a
    # quiz must not erase the fact that the attempt happened.
    flashcard_id = Column(Integer, ForeignKey("flashcards.id", ondelete="SET NULL"), nullable=True)
    quiz_session_id = Column(Integer, ForeignKey("quiz_sessions.id", ondelete="SET NULL"), nullable=True)

    source = Column(String, nullable=False)  # quiz | study
    # None means the attempt was skipped: no evidence either way about recall.
    # The KT model must exclude these rather than read them as incorrect.
    correct = Column(Boolean, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    responded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="interactions")
    concept = relationship("Concept", back_populates="interactions")
