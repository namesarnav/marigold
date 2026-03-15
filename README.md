## FlashLearn

FlashLearn is a simple study app where you upload PDF notes and get AI-generated flashcards and timed quizzes.

### Tech Stack

- **Frontend**: React, Vite, Tailwind CSS
- **Backend**: FastAPI (Python)
- **Database**: SQLite + SQLAlchemy ORM
- **AI**: Google Gemini 1.5 Flash API
- **PDF parsing**: PyPDF2

### Setup

#### 1. Environment

Create a virtual environment using `pyenv` / `python -m venv` and activate it.

Copy `.env.example` to `.env` in the project root and fill in your values:

```bash
cp .env.example .env
```

Required variables:

- `GEMINI_API_KEY` — your Gemini API key
- `DATABASE_URL` — defaults to `sqlite:///./flashlearn.db`
- `CORS_ORIGINS` — usually `http://localhost:5173`

#### 2. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

Key endpoints:

- `POST /api/upload` — upload a PDF, returns `doc_id`
- `GET /api/flashcards/{doc_id}` — list flashcards for a document
- `POST /api/quiz/start` — start a quiz for a document
- `POST /api/quiz/answer` — submit an answer, returns next question or completion
- `GET /api/quiz/results/{quiz_id}` — quiz results

#### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

### Usage Flow

1. Upload a PDF from the homepage (drag and drop or file picker).
2. Wait for flashcards to be generated (spinner shows progress).
3. Review flashcards (click to flip between question and answer).
4. Choose quiz size (5 / 10 / 15) and take a timed quiz (30s/question).
5. View results: score, time taken, and list of wrong answers with corrections.

### Notes

- No authentication is implemented; everything is anonymous and local.
- Errors from Gemini or PDF parsing are surfaced as user-friendly messages in the UI.
- Layout is responsive and tuned for both desktop and mobile.

