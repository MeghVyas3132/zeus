import express, { type Express } from "express";
import { runAgentRouter } from "./routes/run-agent.js";
import { runQueryRouter } from "./routes/run-query.js";
import { buildErrorEnvelope } from "./error-envelope.js";
import { config } from "./config.js";
import { getRedis } from "./redis.js";
import { getPool } from "./db.js";

export function createApp(): Express {
  const app = express();

  app.use(express.json({ limit: "1mb" }));

  // ── CORS — allow cross-origin requests from any frontend ──
  app.use((req: express.Request, res: express.Response, next: express.NextFunction) => {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With");
    if (req.method === "OPTIONS") {
      res.sendStatus(204);
      return;
    }
    next();
  });

  // ── Health check with real connectivity ──────────────────
  app.get("/health", async (_req, res) => {
    const checks: Record<string, string> = {
      gateway: "ok",
      worker: "unknown",
      agent: "unknown",
      postgres: "unknown",
      redis: "unknown",
    };

    // Redis ping
    try {
      const redis = getRedis();
      const pong = await redis.ping();
      checks.redis = pong === "PONG" ? "ok" : "degraded";
    } catch {
      checks.redis = "error";
    }

    // PostgreSQL connectivity
    try {
      const pool = getPool();
      const result = await pool.query("SELECT 1 AS alive");
      checks.postgres = result.rows[0]?.alive === 1 ? "ok" : "degraded";
    } catch {
      checks.postgres = "error";
    }

    // Agent HTTP health
    try {
      const resp = await fetch(`${config.agentBaseUrl}/health`, {
        signal: AbortSignal.timeout(3000),
      });
      checks.agent = resp.ok ? "ok" : "degraded";
    } catch {
      checks.agent = "error";
    }

    // Worker check: see if BullMQ queue has active workers
    // For now, mark as "ok" if Redis is ok (worker registers via BullMQ)
    checks.worker = checks.redis === "ok" ? "ok" : "error";

    const overallOk = checks.gateway === "ok" && checks.redis === "ok" && checks.postgres === "ok";
    const statusCode = overallOk ? 200 : 503;

    res.status(statusCode).json({
      ...checks,
      outputs_dir: config.outputsDir,
      timestamp: new Date().toISOString()
    });
  });

  app.use(runAgentRouter);
  app.use(runQueryRouter);

  app.use((_req, res) => {
    res.status(404).json(buildErrorEnvelope("NOT_FOUND", "Endpoint not found"));
  });

  app.use((err: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    const message = err instanceof Error ? err.message : "Unhandled gateway error";
    res.status(500).json(buildErrorEnvelope("INTERNAL_ERROR", message));
  });

  return app;
}
