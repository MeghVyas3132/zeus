import express from "express";
import { runAgentRouter } from "./routes/run-agent.js";
import { runQueryRouter } from "./routes/run-query.js";
import { buildErrorEnvelope } from "./error-envelope.js";
import { config } from "./config.js";

export function createApp() {
  const app = express();

  app.use(express.json({ limit: "1mb" }));

  app.get("/health", (_req, res) => {
    res.status(200).json({
      gateway: "ok",
      worker: "unknown",
      agent: "unknown",
      postgres: "unknown",
      redis: "unknown",
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
