## users

| Column          | Type      | Constraints                  |
|-----------------|-----------|------------------------------|
| id              | INTEGER   | PK, auto-increment, indexed  |
| email           | TEXT      | NOT NULL, UNIQUE, indexed    |
| password_hash   | TEXT      | NOT NULL                     |
| name            | TEXT      | NOT NULL                     |
| created_at      | DATETIME  | default: utcnow              |

---

## refresh_tokens

| Column      | Type     | Constraints               |
|-------------|----------|---------------------------|
| id          | INTEGER  | PK, auto-increment        |
| user_id     | INTEGER  | FK → users.id, NOT NULL   |
| token_hash  | TEXT     | NOT NULL, UNIQUE          |
| expires_at  | DATETIME | NOT NULL                  |
| revoked     | BOOLEAN  | default: false            |

`token_hash` is SHA-256 of the raw token. Raw tokens are never stored.
Tokens are revoked (not deleted) on logout and on rotation during refresh.

---

## documents

| Column          | Type     | Constraints               |
|-----------------|----------|---------------------------|
| id              | INTEGER  | PK, auto-increment        |
| user_id         | INTEGER  | FK → users.id, NOT NULL   |
| filename        | TEXT     | NOT NULL                  |
| page_count      | INTEGER  | default: 0                |
| status          | TEXT     | default: "processing"     |
| created_at      | DATETIME | default: utcnow           |
| extracted_text  | TEXT     | nullable                  |

`status` values: `processing` → `ready` or `failed`
`extracted_text` is retained to support flashcard regeneration without re-uploading.

---

## flashcards

| Column      | Type     | Constraints                      |
|-------------|----------|----------------------------------|
| id          | INTEGER  | PK, auto-increment               |
| doc_id      | INTEGER  | FK → documents.id, NOT NULL, indexed |
| question    | TEXT     | NOT NULL                         |
| answer      | TEXT     | NOT NULL                         |
| topic       | TEXT     | nullable                         |
| distractors | TEXT     | nullable — JSON array of strings |

`distractors` stores up to 3 wrong answer options as a JSON string (e.g. `["Java", "C++", "Rust"]`). SQLite has no native JSON column, so it is stored as TEXT and parsed in application code.

---

## quiz_sessions

| Column          | Type     | Constraints               |
|-----------------|----------|---------------------------|
| id              | INTEGER  | PK, auto-increment        |
| user_id         | INTEGER  | FK → users.id, NOT NULL   |
| doc_id          | INTEGER  | FK → documents.id, NOT NULL |
| started_at      | DATETIME | default: utcnow           |
| completed_at    | DATETIME | nullable                  |
| score           | INTEGER  | nullable                  |
| total_questions | INTEGER  | nullable                  |
| status          | TEXT     | default: "active"         |

`status` values: `active` → `completed`
`score` is the count of correct answers, set when status transitions to `completed`.

---

## quiz_answers

| Column             | Type    | Constraints                        |
|--------------------|---------|------------------------------------|
| id                 | INTEGER | PK, auto-increment                 |
| session_id         | INTEGER | FK → quiz_sessions.id, NOT NULL    |
| flashcard_id       | INTEGER | FK → flashcards.id, NOT NULL       |
| user_answer        | TEXT    | nullable                           |
| is_correct         | INTEGER | nullable — 1=correct, 0=wrong, NULL=skipped |
| time_taken_seconds | REAL    | nullable                           |

One row per question answered or skipped in a session.

---

## user_stats

| Column              | Type    | Constraints                                  |
|---------------------|---------|----------------------------------------------|
| id                  | INTEGER | PK, auto-increment                           |
| user_id             | INTEGER | FK → users.id, NOT NULL                      |
| date                | DATE    | NOT NULL                                     |
| quizzes_taken       | INTEGER | default: 0                                   |
| flashcards_reviewed | INTEGER | default: 0                                   |

Unique constraint on `(user_id, date)`. One row per user per day, upserted on activity. Used to calculate login streak and lifetime totals.

---

## Relationships

```
users
├── refresh_tokens   (cascade delete)
├── documents        (cascade delete)
│   └── flashcards   (cascade delete)
│       └── quiz_answers (cascade delete)
├── quiz_sessions    (cascade delete)
│   └── quiz_answers (cascade delete)
└── user_stats       (cascade delete)
```
