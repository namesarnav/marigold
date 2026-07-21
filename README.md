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
| `ml/` | Knowledge tracing (SAKT) and concept clustering. A library — the API does not import it yet |
| `infra/` | Terraform for AWS, and the Kubernetes manifests in `infra/k8s/` |

## Stack

- **Backend** — FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic
- **Database** — PostgreSQL (SQLite is used only by the test suite)
- **Cache** — Redis, for login rate-limit counters
- **Auth** — JWT + bcrypt, email verification, password reset, Google/GitHub OAuth
- **AI** — Google Gemini 2.5 Flash for card generation; PyMuPDF for PDF text
- **ML** — PyTorch, sentence-transformers, scikit-learn
- **Deployment** — single-node k3s on EC2 Graviton, Traefik ingress, Let's Encrypt

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

See the header of [`docker-compose.yml`](docker-compose.yml) for what this
setup does *not* exercise (Kubernetes, TLS, real email delivery).

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

Production is a single k3s node on EC2 Graviton, inside a ~$20/month budget
that shapes most of the architecture — Postgres and Redis run in-cluster rather
than as RDS and ElastiCache, and Traefik is the ingress rather than an ALB.

The full runbook, the cost breakdown, and the reasoning behind each choice are
in **[`infra/README.md`](infra/README.md)**.

Merging to `main` builds an arm64 image, pushes it to ECR, and rolls it out over
SSM. No AWS credentials are stored in GitHub: CI assumes a role scoped to this
repository via OIDC, and application secrets are read by the node itself from
SSM Parameter Store.

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
| `GET /healthz` | Liveness and readiness; touches the database |

## Status

Working: accounts and OAuth, PDF upload with background card generation,
flashcards, quizzes, stats, and the interaction log. The ML pipeline is
validated against ASSISTments 2009 (held-out AUC 0.7535) but is **not yet wired
into the product** — there is no scheduling endpoint, and nothing imports `ml/`.
That is the next piece of work; see the end of `infra/README.md`.
