# The API service. Python only — no frontend build, no static bundle.
#
# This is half of a two-service deployment: the React app is built and served
# by frontend/Dockerfile as a separate Railway service. The two talk over the
# public internet, which is why CORS_ORIGINS and COOKIE_SAMESITE have to be
# configured here rather than being irrelevant as they were when one image
# served both.
#
# Build from the REPOSITORY ROOT, not from backend/:
#   docker build -f backend/Dockerfile -t marigold-api .
# It needs alembic.ini and ml/, which live above this file.

FROM python:3.11-slim

# PYTHONUNBUFFERED so logs reach the Railway log stream as they happen rather
# than sitting in a buffer; PYTHONDONTWRITEBYTECODE so the container filesystem
# is not littered with .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
# The knowledge-tracing library behind /api/review/next. Its torch and numpy
# imports are lazy and no checkpoint ships (see .dockerignore), so this adds
# source files and nothing to requirements.txt.
COPY ml/ ./ml/
# Alembic config and revisions ship in the image so the entrypoint can run
# `alembic upgrade head` from this exact build — the schema and the code that
# expects it are then always the same version.
COPY alembic.ini ./
COPY docker-entrypoint.sh ./

# Run unprivileged. The app writes nothing to its own filesystem: uploaded PDFs
# are parsed in memory and the extracted text goes to the database, so the
# filesystem is disposable and this service needs no volume.
#
# chmod +x explicitly: the executable bit survives a Linux checkout but not
# every path into the build context, and losing it turns into a "permission
# denied" at container start rather than at build.
RUN chmod +x docker-entrypoint.sh \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Migrations then uvicorn, bound to $PORT. Exec form so the entrypoint is not
# wrapped in a second shell; the script itself execs uvicorn, which is what
# makes SIGTERM reach the server on a redeploy.
CMD ["./docker-entrypoint.sh"]
