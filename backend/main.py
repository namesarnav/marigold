import logging
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .database import get_db
from .routes import auth, documents, flashcards, interactions, oauth_routes, quiz, stats

settings = get_settings()

# Give the root logger a handler. Uvicorn configures only its own loggers, so
# without this every `logger.info` in the application goes nowhere and only
# Python's last-resort handler (WARNING and above) produces any output at all.
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# NOTE: no `Base.metadata.create_all` here on purpose. The schema is owned by
# Alembic (`alembic upgrade head`, run by the deployment's init container), so
# that a column added to a model can never be silently created in production
# without a reviewed migration. Tests still build their SQLite schema directly
# from the metadata — see backend/tests/conftest.py.

app = FastAPI(title="Marigold API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=604800,
    # Behind TLS in deployment, plain HTTP locally. Driven by config rather than
    # hardcoded: a session cookie without Secure is sent over cleartext, so this
    # must be true anywhere the app is reachable from the internet.
    https_only=settings.cookie_secure,
    same_site="lax",
)


@app.get("/healthz", tags=["ops"])
def healthz(db: Session = Depends(get_db)):
    """Liveness and readiness probe.

    Touches the database on purpose. A process that is up but cannot reach
    Postgres should not be sent traffic, and returning 200 in that state is how
    a rolling deploy replaces a working pod with a broken one.
    """
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(oauth_routes.router)
app.include_router(documents.router)
app.include_router(flashcards.router)
app.include_router(quiz.router)
app.include_router(stats.router)
app.include_router(interactions.router)

# Serve the built frontend (production). Mounted last: this catches "/" and
# every unmatched path, so it must not shadow the API routers or /healthz.
_dist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
