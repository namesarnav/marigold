# Marigold

Upload PDF notes, get AI-generated flashcards and timed quizzes, and have the
app schedule what to review next based on what you're actually forgetting.

Every graded attempt is recorded as `(concept, correct, response time, when)`.
That log is the input to a knowledge-tracing model in [`ml/`](ml/) which ranks
concepts by how likely you are to have forgotten them.

## Layout

| Directory | What's in it |
| --- | --- |
| `backend/` | FastAPI: auth, PDF ingest, card generation, quizzes, the interaction log |
| `frontend/` | React + Vite + Tailwind |
| `ml/` | Knowledge tracing (SAKT) and concept clustering. Reached from the API through `backend/review.py` |

## Stack

- **Backend** — FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic
- **Database** — PostgreSQL (SQLite is used only by the test suite)
- **Cache** — Redis, for login rate-limit counters
- **Auth** — JWT + bcrypt, email verification, password reset, Google/GitHub OAuth
- **AI** — Google Gemini 2.5 Flash for card generation; PyMuPDF for PDF text
- **ML** — PyTorch, sentence-transformers, scikit-learn
- **Deployment** — Railway, two Docker images: the API, and nginx serving the bundle

## Local development

Requires Docker and Node 20.

```bash
export GEMINI_API_KEY=...      # only needed for card generation
docker compose up -d           # Postgres, Redis, and the API on :8000

cd frontend && npm install && npm run dev    # :5173
```

The API container runs `alembic upgrade head` on start and reloads on edits to
`backend/`. Email is not sent in development — verification and password-reset
links are printed to the log:

```bash
docker compose logs api | grep -A6 'email:console'
```

`docker compose down -v` throws the database away.

### Google / GitHub sign-in locally

The sign-in buttons are rendered from `/api/auth/oauth/providers`, which lists
only the providers the server holds credentials for — so with none set the
login page shows no buttons at all. That is deliberate (a button that answers
503 when clicked is worse than no button), but it does mean a missing Google
button is a configuration state rather than a bug.

To enable it, put the credentials in a `.env` file next to `docker-compose.yml`:

```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

and register this exact callback in the Google console:

```
http://localhost:8000/api/auth/oauth/google/callback
```

Provider sign-ins arrive already email-verified, so they skip the verification
gate entirely — which makes this the quickest way to get a usable account
without configuring email delivery.

See the header of [`docker-compose.yml`](docker-compose.yml) for what this
setup does *not* exercise (the frontend bundle, TLS, real email delivery), and
how to run the production image locally instead.

## Tests

```bash
pytest backend/            # 193 tests, SQLite by default
pytest ml/ -m "not slow"   # 109 tests

# Against the database actually used in production:
TEST_DATABASE_URL=postgresql+psycopg://marigold:devpass@localhost:55432/marigold \
  pytest backend/
```

CI runs the backend suite against Postgres, checks that the models have not
drifted from the migrations, and builds the frontend.

## Migrations

Alembic owns the schema. The application never calls `create_all`, so a model
change without a migration is caught in CI rather than discovered in production.

```bash
alembic revision --autogenerate -m "what changed"
alembic upgrade head
```

## Deployment

Railway: two services built from two Dockerfiles, plus Postgres and Redis.

| Service | Dockerfile | What it runs |
| --- | --- | --- |
| `marigold-api` | `backend/Dockerfile` | Alembic migrations, then FastAPI under uvicorn |
| `marigold-web` | `frontend/Dockerfile` | the React bundle on nginx, which also proxies `/api` to `marigold-api` |

The browser only ever talks to `marigold-web`. nginx forwards `/api/*` to the
API's public URL, so the refresh cookie is first-party: no CORS, no
`SameSite=None`, and sign-in works in Safari, which drops cross-site cookies.

Both images build from the repository root, because the API image needs
`alembic.ini` and `ml/`, which sit above `backend/`.

### Variables

`marigold-api`:

| Variable | Value |
| --- | --- |
| `SECRET_KEY` | output of `openssl rand -hex 32` |
| `GEMINI_API_KEY` | Google AI Studio key |
| `DATABASE_URL` | reference picker: Postgres, `DATABASE_URL` |
| `REDIS_URL` | reference picker: Redis, `REDIS_URL` |
| `PUBLIC_URL` | `https://${{marigold-web.RAILWAY_PUBLIC_DOMAIN}}` |

`marigold-web`:

| Variable | Value |
| --- | --- |
| `BACKEND_URL` | `https://${{marigold-api.RAILWAY_PUBLIC_DOMAIN}}` |

The service names inside `${{...}}` must match the Railway service names
exactly, or Railway passes the text through unresolved.

### Build settings, both services

Settings, Build: builder **Dockerfile**, root directory `/`, Dockerfile path
`backend/Dockerfile` or `frontend/Dockerfile`. Settings, Deploy: health check
path `/healthz`. Without the builder set to Dockerfile, Railway falls back to
Railpack, finds no start command, and fails the build.

### Behaviour worth knowing

Migrations run in the API container's entrypoint, before uvicorn binds. A
failed migration aborts the start, the health check never passes, and Railway
keeps the previous deployment serving. Keep the API at one replica for the same
reason: concurrent starts would race on the migration.

`marigold-web` refuses to start if `BACKEND_URL` is missing or malformed, and
says why in its log.

### Disabled until they are built

- **Email delivery.** `EMAIL_BACKEND=console` only logs messages, so the
  verification gate is off by default and the password reset screens are
  commented out in `App.jsx`. Configure `EMAIL_BACKEND=ses` to bring both back.
- **Paid plans.** There is no billing, so the Pro and Team plans and the billing
  FAQs are commented out in `Pricing.jsx`.

### Running the same shape locally

```bash
docker compose --profile web up -d --build   # open http://localhost:8081
```

`web` builds `frontend/Dockerfile` and proxies `/api` to the `api` service over
the compose network, exactly as Railway does.

## API

`GET /docs` on a running instance serves the generated OpenAPI documentation.
Main routes:

| Route | Purpose |
| --- | --- |
| `POST /api/auth/register`, `/login`, `/verify-email` | Accounts |
| `GET /api/auth/oauth/{provider}/login` | Google / GitHub sign-in |
| `POST /api/documents/upload` | Upload a PDF; returns immediately with `status: processing` |
| `GET /api/documents/{id}` | Poll until `ready` or `failed` |
| `GET /api/flashcards/{doc_id}` | Cards for a document |
| `POST /api/flashcards/{card_id}/review` | Record a study attempt |
| `POST /api/quiz/start`, `/{id}/answer`, `/{id}/results` | Quizzes |
| `GET /api/interactions/me` | The raw attempt log |
| `GET /api/review/next` | Concepts ranked by forgetting risk; `as_of` projects forward |
| `GET /healthz` | Liveness and readiness; touches the database |

## Status

Working: accounts and OAuth, PDF upload with background card generation,
flashcards, quizzes, stats, the interaction log, and a **What to Review** tab on
the dashboard that ranks concepts by forgetting risk, with a projection control
for what will have decayed in a week or a month.

The ML pipeline is validated against ASSISTments 2009 (held-out AUC 0.7535) and
`GET /api/review/next` now serves from it — but **only the cold-start half**.
The SAKT checkpoint's skill ids belong to ASSISTments, not to any user's
concepts, so `concept_to_skill` is empty and every concept is scored by the
population prior plus the forgetting decay. That is the correct behaviour, not a
fallback: the sequence model has nothing to say until it is trained on real
Marigold interactions.

Because of that the API image ships `ml/` **without PyTorch** — the prior path
is pure Python, and `ml/inference/predict.py` imports torch and numpy lazily so
the ~2GB dependency is not paid for a code path that cannot run yet. Turning the
SAKT path on later means: export the interaction log, populate
`concept_to_skill`, train, ship the checkpoint, and add torch to
`backend/requirements.txt`. No application code has to change.

One ordering consequence is a deliberate product choice worth revisiting: a
concept studied once and long forgotten ranks *above* one never studied, because
its estimate has decayed below the prior. `source` and `interaction_count` on
each row are what a UI uses to tell those apart.
