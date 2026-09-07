import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .database import get_db
from .routes import (
    auth,
    documents,
    flashcards,
    interactions,
    oauth_routes,
    quiz,
    review,
    stats,
)

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


@app.exception_handler(SQLAlchemyError)
def handle_database_error(request: Request, exc: SQLAlchemyError):
    """Turn an unhandled database error into a 500 the browser can actually read.

    Registered as a handler for a specific exception class, which is what makes
    this work: FastAPI routes handlers for `Exception`/500 to
    ServerErrorMiddleware, the outermost layer of the stack — *outside*
    CORSMiddleware. A 500 from there carries no Access-Control-Allow-Origin, so
    a cross-origin caller never sees the response at all; fetch rejects with
    "Failed to fetch" and the real error is visible only in the server log.

    That is not hypothetical. Regenerating a document's cards after taking a
    quiz on it raised a ForeignKeyViolation, and the entire symptom reaching the
    user was "failed to fetch" — no status, no message, nothing to search for.
    Handlers for a named class are held by ExceptionMiddleware instead, which
    sits inside the user middleware, so this response passes back out through
    CORS and arrives as a readable 500.

    It matters in development, where the Vite server on :5173 is a different
    origin from the API on :8000. In production both are the same origin and the
    500 would have been legible either way — so the mode that hides the error is
    exactly the one used for debugging.

    The detail is deliberately generic: the exception text contains table and
    constraint names. The traceback goes to the log.
    """
    logging.getLogger(__name__).exception(
        "database error handling %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "A database error occurred. Please try again."},
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
app.include_router(review.router)

# --- The built frontend ------------------------------------------------------
#
# One service serves both the API and the React bundle, which is why there is no
# CORS configuration to get right in production and why the session cookie is
# same-origin. In development this directory does not exist and the mount is
# skipped: Vite serves the frontend on :5173 instead.
#
# normpath, not just abspath: the join goes up through "..", and the traversal
# check in `mount_frontend` compares this prefix against an already-normalised
# candidate path. Leaving the ".." in would make every comparison fail and turn
# the guard into "serve index.html for everything", silently.
FRONTEND_DIST = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
)


def mount_frontend(target: FastAPI, dist: str) -> bool:
    """Serve the built bundle from `dist`, with a client-side routing fallback.

    A function rather than module-level statements so the behaviour is testable:
    `frontend/dist` is a build artefact and does not exist in a checkout, so a
    test against the real path would be skipped in CI — which is exactly where
    the fallback would regress unnoticed.

    Returns whether anything was mounted.
    """
    if not os.path.isdir(dist):
        return False

    assets = os.path.join(dist, "assets")
    if os.path.isdir(assets):
        # Hashed filenames, so these are safe to mount on their own prefix and
        # let the browser cache. Mounted ahead of the catch-all below, otherwise
        # a missing asset would be answered with index.html — an HTML body
        # served as JavaScript, which fails in the console rather than in the
        # network tab and is miserable to debug.
        target.mount("/assets", StaticFiles(directory=assets), name="assets")

    index = os.path.join(dist, "index.html")

    @target.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        """Serve a real file if there is one, otherwise index.html.

        The router is a `BrowserRouter`, so /dashboard is a client-side route
        with no file behind it. `StaticFiles(html=True)` alone answers those
        with 404: the app worked when navigated to from the landing page and
        broke on refresh or on a pasted link. This hands unmatched paths to
        index.html and lets React Router resolve them.

        Registered last so the API routers and /healthz match first. Unmatched
        /api/* is excluded deliberately — returning the HTML shell for a
        mistyped endpoint turns a 404 into a JSON parse error at the caller.
        """
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        candidate = os.path.normpath(os.path.join(dist, full_path))
        # normpath collapses any "..", and this check rejects what it resolves
        # to outside the bundle — path traversal is otherwise a file read of
        # anything the app user can open.
        if (
            full_path
            and candidate.startswith(dist + os.sep)
            and os.path.isfile(candidate)
        ):
            return FileResponse(candidate)

        return FileResponse(index)

    return True


mount_frontend(app, FRONTEND_DIST)
