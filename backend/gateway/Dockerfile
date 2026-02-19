FROM node:20-alpine AS builder

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

# Copy workspace root files
COPY package.json pnpm-workspace.yaml tsconfig.base.json ./

# Copy workspace packages
COPY packages/contracts/package.json ./packages/contracts/package.json
COPY packages/contracts/tsconfig.json ./packages/contracts/tsconfig.json
COPY packages/contracts/src ./packages/contracts/src
COPY packages/contracts/schemas ./packages/contracts/schemas

# Copy gateway package
COPY backend/gateway/package.json ./backend/gateway/package.json
COPY backend/gateway/tsconfig.json ./backend/gateway/tsconfig.json
COPY backend/gateway/src ./backend/gateway/src

# Install deps using pnpm and build
RUN pnpm install --frozen-lockfile || pnpm install
RUN pnpm run build

# ── Runtime stage ───────────────────────────────────────
FROM node:20-alpine AS runtime

WORKDIR /app

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/packages/contracts/dist ./packages/contracts/dist
COPY --from=builder /app/packages/contracts/package.json ./packages/contracts/package.json
COPY --from=builder /app/packages/contracts/schemas ./packages/contracts/schemas
COPY --from=builder /app/backend/gateway/dist ./backend/gateway/dist
COPY --from=builder /app/backend/gateway/package.json ./backend/gateway/package.json
COPY --from=builder /app/backend/gateway/node_modules ./backend/gateway/node_modules

ENV PORT=3000
ENV OUTPUTS_DIR=/app/outputs

RUN mkdir -p /app/outputs

EXPOSE 3000

CMD ["node", "backend/gateway/dist/server.js"]
