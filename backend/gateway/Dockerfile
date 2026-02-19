FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json tsconfig.base.json ./
COPY pnpm-workspace.yaml ./
COPY packages/contracts ./packages/contracts
COPY backend/gateway ./backend/gateway

RUN npm install
RUN npm run build

FROM node:20-alpine AS runtime

WORKDIR /app

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/packages/contracts/dist ./packages/contracts/dist
COPY --from=builder /app/packages/contracts/schemas ./packages/contracts/schemas
COPY --from=builder /app/backend/gateway/dist ./backend/gateway/dist

ENV PORT=3000
ENV OUTPUTS_DIR=/app/outputs

RUN mkdir -p /app/outputs

EXPOSE 3000

CMD ["node", "backend/gateway/dist/server.js"]
