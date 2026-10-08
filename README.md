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
| `scripts/`, `eval/` | `eval_rag.py`, comparing the two generation modes, and its labels |

## Stack

- **Backend** — FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic
- **Database** — PostgreSQL 16 with [pgvector](https://github.com/pgvector/pgvector), for chunk embeddings
- **Cache** — Redis, for login rate-limit counters
- **Auth** — JWT + bcrypt, email verification, password reset, Google/GitHub OAuth
- **AI** — Google Gemini for card generation (`GEMINI_MODEL`, default
  `gemini-3.8-flash`) and embeddings (`GEMINI_EMBEDDING_MODEL`, default
  `gemini-embedding-2`); PyMuPDF for PDF text
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

**Upgrading an existing checkout.** Postgres now runs on the
`pgvector/pgvector:pg16` image with a new volume, `pgvector-data`. The old
`pgdata` volume is left untouched, not reused: the old image was Alpine and
this one is Debian, and the two sort text differently, so reusing the data
directory risks silently corrupted indexes. To bring old local data across:

```bash
docker run --rm -v marigold-dev_pgdata:/var/lib/postgresql/data -p 55499:5432 \
  -d --name old-pg postgres:16-alpine && sleep 5
pg_dump --format=custom --no-owner "postgresql://marigold:devpass@localhost:55499/marigold" -f old.dump
docker rm -f old-pg
docker compose up -d postgres          # only Postgres: the new database is still empty
pg_restore --no-owner --dbname "postgresql://marigold:devpass@localhost:55432/marigold" old.dump
docker compose up -d                  # the API's startup migration adds the new tables
```

Restore before starting the API, so the dump lands in an empty database and the
migration then upgrades it like any other. The new volume's first start
also creates `marigold_test` and `marigold_eval`.

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
docker compose up -d postgres   # pgvector Postgres; creates marigold_test
pytest backend/                 # 354 tests
pytest ml/ -m "not slow"        # 109 tests
```

The backend suite runs only against PostgreSQL with pgvector — retrieval is a
vector query, which SQLite cannot run. It defaults to the compose server's
`marigold_test` database (`TEST_DATABASE_URL` overrides it) and refuses any
database whose name does not end in `_test`, because it drops every table after
each test. It makes no network calls: Gemini generation and embeddings are faked
(`backend/tests/fakes.py`), and constructing a real Gemini client fails the test.

CI runs the backend suite against the same pgvector image, round-trips the
migrations, checks that the models have not drifted from them, and builds the
frontend.

## Card generation

`GENERATION_MODE` selects how cards are made; upload and regenerate both obey
it.

- **`full`** (default): one Gemini call over the document's whole text. No citations.
- **`rag`**: Gemini picks topics from a sample of the document; each topic
  retrieves its nearest chunks from that document; one call per topic writes
  cards from only those chunks, citing the chunk ids it used. Cards citing a
  chunk they were not shown are dropped. Each card is shown "From page N" in study
  mode and quiz review.

Every upload is split into overlapping ~650-token chunks with page ranges and
embedded, whatever the mode, so a document can be regenerated in either.
Documents uploaded before this existed have no chunks (their page boundaries
were never stored); `rag` falls back to `full` for them until re-uploaded.

Regenerating replaces a deck only after the new cards exist, so a failed
generation leaves the old deck intact. Interaction history survives either way
(`interactions.flashcard_id` is `ON DELETE SET NULL`).

The design, the reasons behind it (including why per-document retrieval is
exact rather than going through the HNSW index), and the evaluation are in
[`docs/generation.md`](docs/generation.md).

| Variable | Default | |
| --- | --- | --- |
| `GENERATION_MODE` | `full` | `full` or `rag` |
| `GEMINI_MODEL` | `gemini-3.8-flash` | generation model |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-2` | changing model or dimension means re-embedding every chunk |
| `CARDS_PER_UPLOAD` | `15` | |
| `RAG_TOP_K` | `5` | chunks retrieved per topic |
| `RAG_TOPIC_COUNT` | `5` | |
| `EMBEDDING_BATCH_SIZE` | `50` | texts per embedding request |
| `CHUNK_TARGET_TOKENS` / `CHUNK_MAX_TOKENS` / `CHUNK_OVERLAP_TOKENS` | `650` / `800` / `100` | estimated tokens (4 chars each) |

The embedding width is `EMBEDDING_DIM = 768` in `backend/config.py`, not an env
var: it is part of the schema (`vector(768)`).

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
| `GENERATION_MODE` | optional: `full` (default) or `rag`; see [Card generation](#card-generation) |

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

### Postgres with pgvector

The API needs the `vector` extension (pgvector 0.5 or newer, for HNSW).
**Railway's default Postgres template does not include it**, and Railway's docs
say extensions will not be added to it; `CREATE EXTENSION vector` fails there
with `extension "vector" is not available`. The migration that adds
`document_chunks` checks for the extension first and stops with an explanation,
so deploying to a server without it fails the deploy — and, per the behaviour
above, Railway keeps the previous deployment serving.

Switch the database **before** deploying this version:

1. Add a pgvector-enabled Postgres from Railway's template marketplace (search
   "pgvector"), or a service from the `pgvector/pgvector:pg16` image with a
   volume. Use the same Postgres major version as the current database, or
   newer.
2. Put the app in maintenance (scale `marigold-api` to zero) so nothing writes
   during the copy.
3. Copy the data. `pg_dump` must be at least the source server's major version:

   ```bash
   pg_dump --format=custom --no-owner --no-acl "$OLD_DATABASE_URL" -f marigold.dump
   pg_restore --no-owner --no-acl --dbname "$NEW_DATABASE_URL" marigold.dump
   psql "$NEW_DATABASE_URL" -c 'select count(*) from users; select version_num from alembic_version;'
   ```

   Compare the row counts with the old database before going further.
4. Point `marigold-api`'s `DATABASE_URL` at the new service and deploy. The
   migration enables the extension and creates the new tables.
5. Keep the old Postgres until you are satisfied; deleting it is the only
   irreversible step.

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

## Evaluation

```bash
cp ~/papers/*.pdf eval/docs/                       # PDFs stay local (gitignored)
python -m scripts.eval_rag --write-label-template  # only if eval/labels.json is absent
# fill in eval/labels.json: queries and the pages that answer them
python -m scripts.eval_rag --price-input X --price-output Y --price-embed Z
```

Runs both modes on every PDF and writes `report.json`, `report.md` and
`manual_sample.json` (20 random cards to check by hand) to
`eval/results/<timestamp>/`. It makes real Gemini calls and writes only to a
database named `*_eval` (`EVAL_DATABASE_URL`, default the compose server's
`marigold_eval`). What each metric measures, and when it is reported as null
instead, is in [`docs/generation.md`](docs/generation.md#evaluation).

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
