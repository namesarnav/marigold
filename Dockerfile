# Marigold: one image serving the FastAPI API and the built Vite bundle.
#
# This is what Railway builds and runs (see railway.json). One service, one
# image: the API also serves the frontend's static files, so there is no second
# deployment, no CORS between them, and no cross-origin cookie problem.
#
#   docker build -t marigold .
#   docker run --rm -p 8000:8000 --env-file .env marigold
#
# Stage 1: build the frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the Python service.
#
# Split into `backend` and `production` so local development can build only the
# first: docker-compose targets `backend` and skips the npm build entirely,
# which turns a dev rebuild from about a minute into a few seconds. The Vite dev
# server runs on the host against this API.
FROM python:3.11-slim AS backend

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
# Alembic config and revisions ship in the image so the entrypoint can run
# `alembic upgrade head` from this exact build — the schema and the code that
# expects it are then always the same version.
COPY alembic.ini ./
COPY docker-entrypoint.sh ./

# Run unprivileged. A container process does not need root, and the app writes
# nothing to its own filesystem — uploaded PDFs are parsed in memory and the
# extracted text goes to the database, so the filesystem is disposable. That is
# also why this deploys to Railway with no attached volume.
# chmod +x explicitly: the executable bit survives a Linux checkout but not
# every path into the build context (a zip upload, a Windows clone), and losing
# it turns into a "permission denied" at container start rather than at build.
RUN chmod +x docker-entrypoint.sh \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Stage 3: what actually ships. Adds the built frontend, which the API serves
# as static files. This is the default target, so a plain `docker build` and
# Railway both get the full image.
FROM backend AS production

# --chown because the backend stage already switched to the unprivileged user;
# without it these land owned by root.
COPY --chown=app:app --from=frontend-build /app/frontend/dist ./frontend/dist

# Migrations then uvicorn, bound to $PORT. Exec form so the entrypoint script
# is not wrapped in a second shell; the script itself execs uvicorn, which is
# what makes SIGTERM reach the server on a redeploy.
CMD ["./docker-entrypoint.sh"]
