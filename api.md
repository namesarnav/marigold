# API Reference

Base URL: `http://localhost:8000` (dev) — same origin in production.

All endpoints except `/api/auth/register`, `/api/auth/login`, and `/api/auth/refresh` require authentication.

**Authentication:** Bearer token in `Authorization` header, or session cookie set automatically on login/register.

```
Authorization: Bearer <access_token>
```

---

## Auth

### POST /api/auth/register

Create a new account. Sets a `refresh_token` httpOnly cookie.

**Body**
```json
{
  "email": "user@example.com",
  "password": "secret",
  "name": "Jane Doe"
}
```

**Response 200**
```json
{ "access_token": "eyJ...", "token_type": "bearer" }
```

**Errors:** `409` email already registered · `422` invalid email

---

### POST /api/auth/login

Authenticate an existing user. Sets a `refresh_token` httpOnly cookie.

**Body**
```json
{ "email": "user@example.com", "password": "secret" }
```

**Response 200**
```json
{ "access_token": "eyJ...", "token_type": "bearer" }
```

**Errors:** `401` invalid credentials

---

### POST /api/auth/refresh

Issue a new access token using the `refresh_token` cookie. Rotates the refresh token (old one is revoked).

**Cookies:** `refresh_token` (httpOnly, set on login/register)

**Response 200**
```json
{ "access_token": "eyJ...", "token_type": "bearer" }
```

**Errors:** `401` missing, expired, or revoked refresh token

---

### POST /api/auth/logout

Revoke the current refresh token and clear the session.

**Response 200**
```json
{ "message": "Logged out" }
```

---

### GET /api/auth/me

Return the authenticated user's profile.

**Response 200**
```json
{ "id": 1, "email": "user@example.com", "name": "Jane Doe" }
```

**Errors:** `401` not authenticated

---

## Documents

### POST /api/documents/upload

Upload a PDF. Extracts text, calls Gemini to generate 15 flashcards, and stores them. Returns immediately once done.

**Content-Type:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| file  | file | PDF file    |

**Response 200**
```json
{ "doc_id": 42 }
```

**Errors:** `400` not a PDF or no extractable text · `500` Gemini generation failed

---

### GET /api/documents

List all documents belonging to the authenticated user, newest first.

**Response 200**
```json
[
  {
    "id": 42,
    "filename": "lecture.pdf",
    "page_count": 12,
    "status": "ready",
    "created_at": "2024-11-01T10:00:00"
  }
]
```

`status` values: `processing` · `ready` · `failed`

---

### GET /api/documents/{doc_id}

Get a single document.

**Response 200** — same shape as one item from `GET /api/documents`

**Errors:** `404` not found or belongs to another user

---

### PATCH /api/documents/{doc_id}

Rename a document.

**Body**
```json
{ "filename": "new name.pdf" }
```

**Response 200** — updated document object

**Errors:** `404` not found

---

### DELETE /api/documents/{doc_id}

Delete a document and all its flashcards and quiz sessions (cascade).

**Response 204** No Content

**Errors:** `404` not found

---

## Flashcards

### GET /api/flashcards/{doc_id}

Get all flashcards for a document. Options (correct answer + up to 3 distractors) are shuffled on each request. Also increments the user's `flashcards_reviewed` stat for today.

**Response 200**
```json
[
  {
    "id": 7,
    "question": "What is Python?",
    "answer": "A high-level programming language",
    "topic": "Python",
    "options": ["Java", "A high-level programming language", "C++", "Rust"]
  }
]
```

**Errors:** `404` document not found or no flashcards exist

---

### POST /api/flashcards/{doc_id}/new

Manually create a flashcard for a document.

**Body**
```json
{
  "question": "What is a list?",
  "answer": "An ordered, mutable collection",
  "topic": "Python"
}
```

`topic` is optional.

**Response 200** — the created flashcard object

**Errors:** `404` document not found

---

### PATCH /api/flashcards/{card_id}

Edit a flashcard's question, answer, and/or topic. All fields are optional.

**Body**
```json
{
  "question": "Updated question?",
  "answer": "Updated answer",
  "topic": "Updated topic"
}
```

**Response 200** — updated flashcard object

**Errors:** `404` flashcard not found

---

### DELETE /api/flashcards/{card_id}

Delete a single flashcard.

**Response 204** No Content

**Errors:** `404` flashcard not found

---

### POST /api/flashcards/{doc_id}/regenerate

Delete all existing flashcards for the document and regenerate 15 new ones using the originally extracted text. Does not require re-uploading the PDF.

**Response 200** — array of new flashcard objects

**Errors:** `400` document still processing or no stored text · `404` document not found · `500` Gemini failed

---

## Quiz

### POST /api/quiz/start

Start a new quiz session for a document. Returns the first question with shuffled options.

**Body**
```json
{ "doc_id": 42, "num_questions": 10 }
```

`num_questions` is capped at the number of available flashcards.

**Response 200**
```json
{
  "quiz_id": 5,
  "question": {
    "question_id": 7,
    "text": "What is Python?",
    "options": ["Java", "A high-level programming language", "C++", "Rust"],
    "question_number": 1,
    "total_questions": 10,
    "time_limit_seconds": 30
  }
}
```

**Errors:** `404` document not found or has no flashcards

---

### POST /api/quiz/{quiz_id}/answer

Submit an answer for the current question. Returns the next question, or signals completion.

**Body**
```json
{ "answer": "A high-level programming language", "time_taken_seconds": 8.4 }
```

**Response 200 — next question**
```json
{
  "completed": false,
  "quiz_id": 5,
  "question": { ...same shape as above... }
}
```

**Response 200 — quiz complete**
```json
{ "completed": true, "quiz_id": 5 }
```

**Errors:** `400` quiz already completed or all questions answered · `404` session not found

---

### POST /api/quiz/{quiz_id}/skip

Skip the current question (recorded as unanswered). Same response shape as `/answer`.

**Body**
```json
{ "time_taken_seconds": 30.0 }
```

**Response 200** — same as `/answer`

**Errors:** `400` · `404`

---

### GET /api/quiz/{quiz_id}/results

Get the final score for a completed quiz.

**Response 200**
```json
{
  "score": 8,
  "total": 10,
  "percentage": 80.0,
  "time_taken_seconds": 94.5,
  "wrong_answers": [
    {
      "question": "What is a tuple?",
      "your_answer": "A mutable sequence",
      "correct_answer": "An immutable sequence"
    }
  ]
}
```

**Errors:** `400` no answers recorded · `404` session not found

---

### GET /api/quiz/{quiz_id}/review

Get a full question-by-question breakdown of a completed quiz.

**Response 200**
```json
{
  "questions": [
    {
      "question": "What is Python?",
      "options": ["A high-level programming language", "C++", "Java", "Rust"],
      "correct_answer": "A high-level programming language",
      "user_answer": "A high-level programming language",
      "is_correct": true,
      "time_taken_seconds": 4.2
    }
  ]
}
```

`is_correct` is `null` for skipped questions. `user_answer` is `null` for skipped questions.

**Errors:** `404` session not found

---

### GET /api/quiz/history

List the 20 most recently completed quizzes for the authenticated user.

**Response 200**
```json
[
  {
    "quiz_id": 5,
    "doc_filename": "lecture.pdf",
    "score": 8,
    "total": 10,
    "percentage": 80.0,
    "completed_at": "2024-11-01T11:30:00"
  }
]
```

---

## Stats

### GET /api/stats/me

Return lifetime stats for the authenticated user.

**Response 200**
```json
{
  "streak": 3,
  "total_quizzes": 12,
  "average_score": 74,
  "total_flashcards_reviewed": 240
}
```

`streak` — consecutive days with any activity (quiz taken or flashcards viewed), counting today if active.
`average_score` — mean percentage across all completed quizzes, rounded to nearest integer.
