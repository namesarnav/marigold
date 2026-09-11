# The frontend service: build the Vite bundle, serve it with nginx.
#
# Build from the REPOSITORY ROOT so the context matches backend/Dockerfile:
#   docker build -f frontend/Dockerfile \
#     --build-arg VITE_API_BASE_URL=https://your-api.up.railway.app \
#     -t marigold-web .
#
# VITE_API_BASE_URL is a BUILD argument, not a runtime variable, and that is
# the thing most likely to catch you out. Vite substitutes import.meta.env at
# compile time and bakes the result into the bundle, so changing it on the
# Railway service requires a REBUILD, not a restart. Railway exposes service
# variables to the build as build args, so setting it in the dashboard is
# enough — but a redeploy without a rebuild will keep the old value.

FROM node:20-alpine AS build
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./

# Empty default is deliberate: it makes the bundle call the same origin it was
# served from, which is what the old single-service deployment wanted. For the
# split deployment this must be the API service's public URL.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine

# nginx cannot read environment variables from its config, and Railway assigns
# the port at runtime. The official image runs envsubst over anything in
# templates/ at startup, so this is how $PORT reaches the listen directive.
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
ENV PORT=8080

COPY --from=build /app/frontend/dist /usr/share/nginx/html

EXPOSE 8080
