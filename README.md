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

Railway, two services built from two Dockerfiles in this repo:

| Service | Dockerfile | What it runs |
| --- | --- | --- |
| API | `backend/Dockerfile` | Alembic migrations, then FastAPI under uvicorn |
| Frontend | `frontend/Dockerfile` | Vite build, served by nginx with an SPA fallback |

Both build from the repository root, because the API image needs `alembic.ini`
and `ml/`, which sit above `backend/`.

The two are separate origins, and that has three consequences that are easy to
miss because each fails silently:

- **`CORS_ORIGINS` must name the frontend's URL.** It is not derived correctly
  for this layout: the Railway default describes the API's own domain, which
  the browser never sends as `Origin`.
- **`COOKIE_SAMESITE` must be `none`.** The refresh token is an `HttpOnly`
  cookie, and a `Lax` cookie is not sent cross-site, so login appears to work
  and every session dies at the first token refresh 15 minutes later. `none`
  requires `COOKIE_SECURE=true`; the config refuses to start on the
  combination browsers would discard. Note Safari blocks third-party cookies
  outright and Chrome is phasing them out, so this is the arrangement's real
  weak point.
- **`VITE_API_BASE_URL` is a build argument, not a runtime variable.** Vite
  substitutes it at compile time, so changing it requires rebuilding the
  frontend service rather than restarting it.

### First deploy

1. **Create the project.** *New Project → Deploy from GitHub repo*, pick this
   repository. Do this twice, once per service, both pointed at the same repo.

2. **Add the databases.** *New → Database → PostgreSQL*, then again for Redis.

3. **Configure the API service.** *Settings → Build → Dockerfile Path* =
   `backend/Dockerfile`, root directory `/`, and *Deploy → Health Check Path* =
   `/healthz`. Then set its variables:

   | Variable | Value |
   | --- | --- |
   | `SECRET_KEY` | `openssl rand -hex 32` |
   | `GEMINI_API_KEY` | Your Google AI Studio key |
   | `DATABASE_URL` | reference to Postgres, added with the variable picker |
   | `REDIS_URL` | reference to Redis, added with the variable picker |
   | `COOKIE_SAMESITE` | `none` |
   | `CORS_ORIGINS` | the frontend service's URL, once it has one |
   | `FRONTEND_BASE_URL` | the frontend service's URL |

   Add the two database URLs with Railway's reference picker rather than
   typing `${{Postgres.DATABASE_URL}}` by hand. A name that does not match the
   service exactly is passed through as literal text, and the first thing to
   read it is SQLAlchemy, which fails with `Could not parse SQLAlchemy URL`.

4. **Configure the frontend service.** *Dockerfile Path* =
   `frontend/Dockerfile`, health check `/healthz`, and one variable:

   | Variable | Value |
   | --- | --- |
   | `VITE_API_BASE_URL` | the API service's public URL |

5. **Generate a domain for each** under *Settings → Networking*. This is also
   what sets `RAILWAY_PUBLIC_DOMAIN`, which the API reads at startup to derive
   `BACKEND_BASE_URL` and `COOKIE_SECURE` — so redeploy the API afterwards, or
   it keeps the localhost defaults it booted with.

Because each service needs the other's domain, expect to deploy once, generate
both domains, fill in the cross-references, and redeploy. The frontend needs a
rebuild rather than a restart for `VITE_API_BASE_URL` to take.

Migrations run in the API container's entrypoint, before uvicorn binds. A
failed migration aborts the start, so the health check never passes and Railway
keeps the previous deployment serving rather than cutting over to a container
whose code and schema disagree. That is also why the API service should stay at
one replica: two starting together would run migrations concurrently, and the
loser can trip its own health check.

### Running the split locally

```bash
docker compose --profile web up -d --build   # API on :8000, nginx on :8081
```

This exercises CORS, but not the cookie: `SameSite=None` requires `Secure`, and
compose serves plain HTTP. Cross-origin auth can only be verified end to end
over HTTPS.

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
