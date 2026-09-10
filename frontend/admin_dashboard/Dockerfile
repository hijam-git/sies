# Multi-stage build for the React SPA.

# ── Stage 1: build ────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# ── Stage 2: static server ────────────────────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

RUN npm install -g serve

COPY --from=builder /app/dist ./dist

# Cache rules for the static server, which reads serve.json from the directory
# it serves.
#
# Without this, index.html could be cached by the browser. Vite gives every
# asset a content hash, so the next deploy publishes new filenames and deletes
# the old ones — a browser still holding yesterday's index.html then requests
# JS that no longer exists, gets the SPA fallback instead, and the dashboard
# fails to boot with a MIME-type error. The HTML must always be re-fetched; the
# hashed assets it names can be cached forever, because a changed file is a
# changed name. config.js is written at container start, so it must not be
# cached either.
COPY serve.json ./dist/serve.json

# Runtime configuration, written at start rather than baked in: the same image
# is what gets promoted from staging to production, and rebuilding to change a
# URL means the thing tested is not the thing shipped.
RUN printf '%s\n' \
    '#!/bin/sh' \
    'cat > /app/dist/config.js <<EOF' \
    'window.ENV = {' \
    '  API_URL: "${API_URL:-/api}"' \
    '};' \
    'EOF' \
    'exec serve -s dist -l 5173' \
    > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 5173

CMD ["/app/entrypoint.sh"]
