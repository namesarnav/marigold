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
- **Deployment** — Railway, one Docker image serving both the API and the bundle

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

Railway, from the [`Dockerfile`](Dockerfile). One service: the multi-stage build
compiles the Vite bundle and the FastAPI app serves it as static files, so there
is no second deployment, no cross-origin CORS, and no third-party cookie
problem. Nothing is written to disk — PDFs are parsed in memory and the
extracted text goes to Postgres — so the service needs no volume.

### First deploy

1. **Create the project.** In Railway, *New Project → Deploy from GitHub repo*,
   and pick this repository. It reads [`railway.toml`](railway.toml) and builds
   the Dockerfile; no other build configuration is needed.

2. **Add the databases.** *New → Database → PostgreSQL*, then again for Redis.

3. **Set the service variables** (*Variables* on the app service):

   | Variable | Value |
   | --- | --- |
   | `SECRET_KEY` | `openssl rand -hex 32` |
   | `GEMINI_API_KEY` | Your Google AI Studio key |
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
   | `REDIS_URL` | `${{Redis.REDIS_URL}}` |

   Use the `${{...}}` reference syntax rather than pasting the URLs: a pasted
   copy goes stale the moment a database is replaced. Every other variable has
   a working default — [`.env.example`](.env.example) documents the full set.

4. **Generate a domain.** *Settings → Networking → Generate Domain*. Railway
   injects it as `RAILWAY_PUBLIC_DOMAIN`, and `backend/config.py` derives
   `FRONTEND_BASE_URL`, `BACKEND_BASE_URL`, `CORS_ORIGINS` and `COOKIE_SECURE`
   from it — so emailed links, OAuth callbacks and the Secure cookie flag are
   all correct without being configured by hand. Setting any of them explicitly
   overrides the derived value, which is how a custom domain is configured.

Migrations run in the container's entrypoint, before uvicorn binds. A failed
migration aborts the start, so the health check never passes and Railway keeps
the previous deployment serving rather than cutting over to a container whose
code and schema disagree.

### After the first deploy

Pushing to `main` redeploys. `/healthz` executes `SELECT 1`, so a container that
is up but cannot reach Postgres is never sent traffic.

Two things are not on by default and are worth knowing about:

- `EMAIL_BACKEND` is `console`, so verification links are printed to the Railway
  logs instead of being sent. Real signups need `EMAIL_BACKEND=ses` and SES
  credentials.
- OAuth buttons only appear for providers with credentials set. Each provider's
  redirect URI is `https://<your-domain>/api/auth/oauth/<provider>/callback`.

### Scaling past one instance

`railway.toml` pins `numReplicas = 1` because the entrypoint migrates on every
start; concurrent replicas would serialise on the migration lock and a loser can
trip its own health check. Moving `alembic upgrade head` out of
[`docker-entrypoint.sh`](docker-entrypoint.sh) into a pre-deploy command is the
prerequisite for raising it.

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
flashcards, quizzes, stats, the interaction log, and a review queue that ranks
concepts by forgetting risk.

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
