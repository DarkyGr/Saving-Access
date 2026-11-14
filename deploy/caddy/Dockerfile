# Production web tier: builds the SPA and serves it with Caddy, which also
# terminates TLS and proxies /api to the backend (task 32.6).
# Build context: repository root (see docker-compose.prod.yml).
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
# Same origin as the API (Caddy proxies /api), so no absolute API URL.
ENV VITE_API_URL=""
RUN npm run build

FROM caddy:2.8-alpine
COPY --from=build /app/dist /srv
COPY deploy/caddy/Caddyfile /etc/caddy/Caddyfile
