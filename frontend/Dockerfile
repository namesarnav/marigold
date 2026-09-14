# The frontend service: build the Vite bundle, serve it with nginx, and proxy
# /api to the API service.
#
# Build from the REPOSITORY ROOT so the context matches backend/Dockerfile:
#   docker build -f frontend/Dockerfile -t marigold-web .
#   docker run -p 8080:8080 -e BACKEND_URL=https://your-api.up.railway.app marigold-web
#
# There is deliberately no build-time API URL. The bundle calls its own origin
# and nginx forwards /api at runtime, so pointing the frontend at a different
# API is a variable change and a restart, never a rebuild. It also means a
# stale VITE_API_BASE_URL left on the Railway service is ignored: without an
# ARG line, Docker never exposes it to the build.

FROM node:20-alpine AS build
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine

# PORT: Railway assigns one at runtime; 8080 keeps `docker run` working.
# NGINX_ENTRYPOINT_LOCAL_RESOLVERS: asks the image to export the container's
# DNS servers as NGINX_LOCAL_RESOLVERS, which the config's `resolver` needs.
ENV PORT=8080 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
# The entrypoint only sources *.envsh files that are executable, and a missing
# bit is skipped with a log line rather than an error, so set it explicitly.
COPY frontend/05-check-backend-url.envsh /docker-entrypoint.d/05-check-backend-url.envsh
RUN chmod +x /docker-entrypoint.d/05-check-backend-url.envsh

COPY --from=build /app/frontend/dist /usr/share/nginx/html

EXPOSE 8080
