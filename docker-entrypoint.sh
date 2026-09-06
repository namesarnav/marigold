#!/bin/sh
# Container entrypoint: bring the schema up to date, then serve.
#
# On Kubernetes this was an init container, which is the better shape — the
# migration runs once, before any app container starts. Railway has no such
# concept: there is one process, so the migration runs here. `set -e` means a
# failed migration aborts the start rather than serving traffic against a
# schema the code does not expect; Railway then keeps the previous deployment
# live, which is the outcome we want.
set -e

# Alembic reads DATABASE_URL through backend.config rather than alembic.ini
# (see backend/migrations/env.py), so this migrates whatever the service is
# actually pointed at — no second place to keep a database URL in step.
echo "==> alembic upgrade head"
alembic upgrade head

# Railway assigns the port at runtime and routes the public domain to it; the
# fallback keeps `docker run -p 8000:8000` working unchanged.
PORT="${PORT:-8000}"

echo "==> uvicorn on :${PORT}"
# exec so uvicorn becomes PID 1 and receives SIGTERM directly. Without it the
# shell holds PID 1, does not forward the signal, and every redeploy waits out
# the full shutdown grace period instead of draining cleanly.
exec uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers "${WEB_CONCURRENCY:-1}" \
  --proxy-headers \
  --forwarded-allow-ips '*'
