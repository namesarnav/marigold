# Marigold: one image serving the FastAPI API and the built Vite bundle.
#
# Targets linux/arm64 — the deployment node is EC2 Graviton (t4g), which cannot
# run an amd64 image. Build it explicitly:
#
#   docker buildx build --platform linux/arm64 -t marigold/app:<sha> .
#
# Stage 1: build the frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the Python service
FROM python:3.11-slim

# PYTHONUNBUFFERED so logs reach kubectl logs as they happen rather than sitting
# in a buffer; PYTHONDONTWRITEBYTECODE so the read-only-ish container filesystem
# is not littered with .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
# Alembic config and revisions ship in the image so the deployment's init
# container can run `alembic upgrade head` from this exact build — the schema
# and the code that expects it are then always the same version.
COPY alembic.ini ./
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Run unprivileged. A container process does not need root, and the app writes
# nothing to its own filesystem — uploads go to the database, artifacts to S3.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000

# Exec form, not shell form. The previous `CMD uvicorn ... ${PORT:-8000}` ran
# under /bin/sh, which does not forward SIGTERM to its child, so every pod took
# the full termination grace period to die instead of shutting down cleanly.
# One worker is deliberate: the node is a 2 GB t4g.small and a second worker
# doubles the resident set for no throughput gain on this workload.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
