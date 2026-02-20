# ── Stage 1: Build ──────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install pnpm
RUN corepack enable && corepack prepare pnpm@9 --activate

# Copy workspace root files for dependency resolution
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY packages/contracts/package.json packages/contracts/
COPY frontend/package.json frontend/

# Install all deps (workspace-aware)
RUN pnpm install --frozen-lockfile || pnpm install

# Copy source
COPY packages/contracts/ packages/contracts/
COPY frontend/ frontend/

# Build contracts first (if needed)
RUN cd packages/contracts && pnpm run build 2>/dev/null || true

# Accept VITE_ build-time args from Railway env vars
ARG VITE_API_BASE_URL=/api
ARG VITE_SOCKET_URL=
ARG VITE_SOCKET_PATH=/socket.io

# Build frontend with injected env vars
RUN cd frontend && \
    VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_SOCKET_URL=${VITE_SOCKET_URL} \
    VITE_SOCKET_PATH=${VITE_SOCKET_PATH} \
    pnpm run build

# ── Stage 2: Serve with nginx ──────────────────────────
FROM nginx:alpine AS production

# Install envsubst for runtime nginx template rendering
RUN apk add --no-cache gettext

# Copy built assets
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

# Runtime-configurable nginx template and entrypoint script
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY frontend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV PORT=80
ENV GATEWAY_UPSTREAM=http://gateway:3000

EXPOSE 80

CMD ["/docker-entrypoint.sh"]
