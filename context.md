
Build a study app called "FlashLearn" where users upload PDF notes or 
lecture slides and get AI-generated flashcards and timed quizzes.

## Tech Stack
- Frontend: React + Vite + Tailwind CSS + shadcn/ui
- Backend: FastAPI (Python)
- Database: SQLite + SQLAlchemy and ORM
- AI: Google Gemini 1.5 Flash API
- PDF parsing: PyPDF2
- Virtual Env: Pyenv 3.13.7

## Features to Build

### 1. PDF Upload
- Drag and drop or click to upload PDF
- Extract text using PyMuPDF on the backend
- Show upload progress
- Store file metadata in SQLite (id, filename, upload_date, status)

### 2. Flashcard Generation
- After upload, send extracted text to Gemini 1.5 Flash
- Prompt Gemini to return exactly this JSON format:
  [{"question": "...", "answer": "...", "topic": "..."}]
- Generate 15 flashcards per PDF
- Store flashcards in SQLite linked to the PDF
- Display as flippable cards (click to reveal answer)
- Show topic tag on each card

### 3. Quiz Mode
- User selects number of questions (5, 10, or 15)
- Countdown timer: 30 seconds per question
- Show question, 4 multiple choice options (1 correct + 3 distractors)
- Generate distractors using Gemini in the same flashcard generation call
- Track: correct answers, time taken, skipped questions
- Store quiz results in SQLite

### 4. Results Screen
- Score as percentage
- Time taken
- List of wrong answers with correct answers shown
- Button to retry or go back to flashcards

## API Endpoints
POST /api/upload         — upload PDF, returns doc_id
GET  /api/flashcards/{doc_id}  — returns flashcards for a doc
POST /api/quiz/start     — takes doc_id + num_questions, returns quiz_id
POST /api/quiz/answer    — takes quiz_id + question_id + answer
GET  /api/quiz/results/{quiz_id} — returns full results

## Database Schema
Table: documents
- id, filename, upload_date, status, page_count

Table: flashcards  
- id, doc_id (FK), question, answer, topic

Table: quiz_sessions
- id, doc_id (FK), started_at, completed_at, score, total_questions

Table: quiz_answers
- id, session_id (FK), flashcard_id (FK), user_answer, is_correct, time_taken

## Gemini Prompt to Use
"""
You are a study assistant. Extract flashcards from the following text.

Return ONLY a JSON array, no markdown, no explanation. Format:
[
  {
    "question": "...",
    "answer": "...",
    "topic": "...",
    "distractors": ["wrong1", "wrong2", "wrong3"]
  }
]

Generate exactly {n} flashcards. Cover the most important concepts.
Text: {extracted_text}
"""

## Environment Variables
GEMINI_API_KEY=your_key_here
DATABASE_URL=sqlite:///./flashlearn.db
CORS_ORIGINS=http://localhost:5173

## Requirements
- Backend runs on port 8000
- Frontend runs on port 5173
- CORS configured between them
- .env file for secrets, never hardcoded
- requirements.txt with pinned versions
- package.json with all dependencies
- README.md with setup instructions (pip install, npm install, how to run)
- Handle errors gracefully: show user-friendly messages if Gemini fails or PDF 
  has no extractable text
- Loading spinners during API calls
- Mobile responsive UI

## Do Not
- Do not use any authentication
- Do not use any paid services other than Gemini API
- Do not use TypeScript
- Do not use Redux or any state management library
- Keep it simple, every file should be readable and straightforward

# TODO: 

Setup 
* Create new folder flashlearn
* Open in Cursor
* Paste the prompt into Cursor Composer (Cmd+I)
* Wait for scaffold to generate
* Create .env file and add your GEMINI_API_KEY

Backend
* using pyenv for virtual env
* cd backend && pip install -r requirements.txt
* Run uvicorn main:app --reload
* Test POST /api/upload with a sample PDF (use Postman or curl)
* Confirm Gemini returns flashcards in terminal logs
* Check flashcards are saved in SQLite

Frontend 
* cd frontend && npm install
* Run npm run dev
* Upload a PDF through the UI — confirm it works
* Flashcards display and flip on click
* Loading spinner shows during API calls

Quiz Mode
* Select number of questions (5, 10, 15)
* Timer counts down per question
* Answer a question — correct/wrong feedback shows
* Complete quiz — results screen shows score
Polish
* Test full flow end to end once
* Make sure no crashes on happy path
* Error message shows if PDF has no text
* Looks decent on mobile

Documentations 
* Write down why you chose FastAPI
* Write down why you chose Gemini 1.5 Flash
* Write down what you'd add next (auth, RAG, PostgreSQL, Docker)
* Practice demoing it out loud once



Here's the full API structure:

---

## Auth Routes `/api/auth`

```
POST   /api/auth/register        — email, password → creates user, returns JWT
POST   /api/auth/login           — email, password → returns JWT + refresh token
POST   /api/auth/refresh         — refresh token → new JWT
POST   /api/auth/logout          — invalidates refresh token
```

---

## User Routes `/api/user`
```
GET    /api/user/me              — returns current user profile
PATCH  /api/user/me              — update name, email
DELETE /api/user/me              — delete account + all data
```

---

## Document Routes `/api/documents`
```
POST   /api/documents/upload     — upload PDF, triggers text extraction + Gemini
GET    /api/documents            — list all docs for current user
GET    /api/documents/{doc_id}   — get single doc metadata
DELETE /api/documents/{doc_id}   — delete doc + its flashcards + quiz history
```

---

## Flashcard Routes `/api/flashcards`
```
GET    /api/flashcards/{doc_id}          — get all flashcards for a doc
POST   /api/flashcards/{doc_id}/regenerate — re-run Gemini, replace flashcards
PATCH  /api/flashcards/{card_id}         — edit a single flashcard manually
DELETE /api/flashcards/{card_id}         — delete a single flashcard
```

---

## Quiz Routes `/api/quiz`
```
POST   /api/quiz/start                   — doc_id + num_questions → returns quiz_id + first question
POST   /api/quiz/{quiz_id}/answer        — question_id + answer → returns correct/wrong + next question
POST   /api/quiz/{quiz_id}/skip          — skip current question
GET    /api/quiz/{quiz_id}/results       — full results after completion
GET    /api/quiz/history                 — all past quizzes for current user
DELETE /api/quiz/{quiz_id}              — delete a quiz session
```

---

## Database Schema

```
users
- id, email, password_hash, name, created_at

refresh_tokens
- id, user_id (FK), token_hash, expires_at, revoked

documents
- id, user_id (FK), filename, s3_key, page_count, status, created_at

flashcards
- id, doc_id (FK), question, answer, topic, distractors (JSON)

quiz_sessions
- id, user_id (FK), doc_id (FK), started_at, completed_at, score, total_questions

quiz_answers
- id, session_id (FK), flashcard_id (FK), user_answer, is_correct, time_taken_seconds
```

---

## JWT Strategy

```
Access token     — expires in 15 minutes, sent in Authorization header
Refresh token    — expires in 7 days, stored in httpOnly cookie
Token rotation   — new refresh token issued on every /refresh call
Revocation       — refresh tokens stored hashed in DB, deleted on logout
```

---

## Every Route Except Auth is Protected

```python
# FastAPI dependency on every protected route
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=401)
    return user
```

---

## Request / Response Examples

**Register**
```json
POST /api/auth/register
{ "email": "user@example.com", "password": "securepass", "name": "John" }

→ 201
{ "access_token": "eyJ...", "token_type": "bearer" }
```

**Upload PDF**
```json
POST /api/documents/upload
Headers: Authorization: Bearer eyJ...
Body: multipart/form-data — file: lecture.pdf

→ 202
{ "doc_id": "abc123", "status": "processing", "message": "Flashcards being generated" }
```

**Start Quiz**
```json
POST /api/quiz/start
{ "doc_id": "abc123", "num_questions": 10 }

→ 200
{
  "quiz_id": "xyz789",
  "question": {
    "id": "q1",
    "text": "What is photosynthesis?",
    "options": ["A: ...", "B: ...", "C: ...", "D: ..."]
  },
  "question_number": 1,
  "total_questions": 10,
  "time_limit_seconds": 30
}
```

**Submit Answer**
```json
POST /api/quiz/xyz789/answer
{ "question_id": "q1", "answer": "A", "time_taken_seconds": 12 }

→ 200
{
  "correct": true,
  "correct_answer": "A",
  "next_question": { ... },
  "question_number": 2
}
```

**Results**
```json
GET /api/quiz/xyz789/results

→ 200
{
  "score": 8,
  "total": 10,
  "percentage": 80,
  "time_taken_seconds": 187,
  "wrong_answers": [
    { "question": "...", "your_answer": "B", "correct_answer": "A" }
  ]
}
```

---

Build in this order: **Auth → Upload → Flashcards → Quiz.** Don't move to the next until the previous works.





Here's the full schema:

---

## PostgreSQL Schema

```sql
-- Users
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name        VARCHAR(255),
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- Refresh Tokens
CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(255) UNIQUE NOT NULL,
    expires_at  TIMESTAMP NOT NULL,
    revoked     BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Documents
CREATE TABLE documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename    VARCHAR(255) NOT NULL,
    s3_key      VARCHAR(500),
    page_count  INTEGER,
    status      VARCHAR(50) DEFAULT 'processing',
                -- processing | ready | failed
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Flashcards
CREATE TABLE flashcards (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id      UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    question    TEXT NOT NULL,
    answer      TEXT NOT NULL,
    topic       VARCHAR(255),
    distractors JSONB,
                -- ["wrong1", "wrong2", "wrong3"]
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Quiz Sessions
CREATE TABLE quiz_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doc_id          UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    started_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP,
    score           INTEGER,
    total_questions INTEGER,
    status          VARCHAR(50) DEFAULT 'in_progress'
                    -- in_progress | completed | abandoned
);

-- Quiz Answers
CREATE TABLE quiz_answers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
    flashcard_id        UUID NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE,
    user_answer         TEXT,
    is_correct          BOOLEAN,
    time_taken_seconds  INTEGER,
    answered_at         TIMESTAMP DEFAULT NOW()
);
```

---

## Indexes

```sql
-- Fastest lookups you'll actually need
CREATE INDEX idx_documents_user_id       ON documents(user_id);
CREATE INDEX idx_flashcards_doc_id       ON flashcards(doc_id);
CREATE INDEX idx_quiz_sessions_user_id   ON quiz_sessions(user_id);
CREATE INDEX idx_quiz_sessions_doc_id    ON quiz_sessions(doc_id);
CREATE INDEX idx_quiz_answers_session_id ON quiz_answers(session_id);
CREATE INDEX idx_refresh_tokens_user_id  ON refresh_tokens(user_id);
```

---

## SQLAlchemy Models (Python)

```python
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import uuid

class User(Base):
    __tablename__ = "users"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email         = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name          = Column(String(255))
    created_at    = Column(TIMESTAMP, server_default=func.now())
    updated_at    = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    documents      = relationship("Document", back_populates="user", cascade="all, delete")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete")
    quiz_sessions  = relationship("QuizSession", back_populates="user", cascade="all, delete")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False)
    revoked    = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    user = relationship("User", back_populates="refresh_tokens")


class Document(Base):
    __tablename__ = "documents"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename   = Column(String(255), nullable=False)
    s3_key     = Column(String(500))
    page_count = Column(Integer)
    status     = Column(String(50), default="processing")
    created_at = Column(TIMESTAMP, server_default=func.now())

    user       = relationship("User", back_populates="documents")
    flashcards = relationship("Flashcard", back_populates="document", cascade="all, delete")
    quizzes    = relationship("QuizSession", back_populates="document", cascade="all, delete")


class Flashcard(Base):
    __tablename__ = "flashcards"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id      = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    question    = Column(Text, nullable=False)
    answer      = Column(Text, nullable=False)
    topic       = Column(String(255))
    distractors = Column(JSONB)
    created_at  = Column(TIMESTAMP, server_default=func.now())

    document     = relationship("Document", back_populates="flashcards")
    quiz_answers = relationship("QuizAnswer", back_populates="flashcard", cascade="all, delete")


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    doc_id          = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    started_at      = Column(TIMESTAMP, server_default=func.now())
    completed_at    = Column(TIMESTAMP)
    score           = Column(Integer)
    total_questions = Column(Integer)
    status          = Column(String(50), default="in_progress")

    user     = relationship("User", back_populates="quiz_sessions")
    document = relationship("Document", back_populates="quizzes")
    answers  = relationship("QuizAnswer", back_populates="session", cascade="all, delete")


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id         = Column(UUID(as_uuid=True), ForeignKey("quiz_sessions.id", ondelete="CASCADE"), nullable=False)
    flashcard_id       = Column(UUID(as_uuid=True), ForeignKey("flashcards.id", ondelete="CASCADE"), nullable=False)
    user_answer        = Column(Text)
    is_correct         = Column(Boolean)
    time_taken_seconds = Column(Integer)
    answered_at        = Column(TIMESTAMP, server_default=func.now())

    session   = relationship("QuizSession", back_populates="answers")
    flashcard = relationship("Flashcard", back_populates="quiz_answers")
```

---

## Alembic Migration Setup

```bash
pip install alembic
alembic init migrations
```

```python
# migrations/env.py — point it to your models
from models import Base
target_metadata = Base.metadata
```

```bash
# Generate and run migrations
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

---

## `.env` Database Config

```
DATABASE_URL=postgresql://user:password@localhost:5432/flashlearn
```