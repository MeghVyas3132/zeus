import { Router, type Router as RouterType } from "express";
import { buildErrorEnvelope } from "../error-envelope.js";
import { config } from "../config.js";
import {
  assertRunId,
  hasReportArtifact,
  readResultsArtifact,
  reportArtifactPath
} from "../artifacts.js";
import { runStore } from "../run-store.js";

export const runQueryRouter: RouterType = Router();

runQueryRouter.get("/agent/status/:runId", async (req, res) => {
  const runId = req.params.runId;

  try {
    assertRunId(runId);
  } catch {
    return res.status(400).json(buildErrorEnvelope("INVALID_INPUT", "Invalid run_id"));
  }

  const active = runStore.getActiveByRunId(runId);

  if (active) {
    return res.status(200).json({
      run_id: active.run_id,
      status: active.status,
      current_node: "queued",
      iteration: 0,
      max_iterations: config.maxIterations,
      progress_pct: 0
    });
  }

  try {
    const results = await readResultsArtifact(config.outputsDir, runId);
    return res.status(200).json({
      run_id: results.run_id,
      status: results.final_status.toLowerCase(),
      current_node: "complete",
      iteration: results.ci_log.length,
      max_iterations: config.maxIterations,
      progress_pct: 100
    });
  } catch {
    // fall through to not-found
  }

  return res.status(404).json(buildErrorEnvelope("NOT_FOUND", "Run not found"));
});

runQueryRouter.get("/results/:runId", async (req, res) => {
  const runId = req.params.runId;

  try {
    const payload = await readResultsArtifact(config.outputsDir, runId);
    return res.status(200).json(payload);
  } catch (error) {
    if (error instanceof Error && error.message.includes("Invalid run_id")) {
      return res.status(400).json(buildErrorEnvelope("INVALID_INPUT", "Invalid run_id"));
    }

    return res.status(404).json(buildErrorEnvelope("NOT_FOUND", "results.json not found"));
  }
});

runQueryRouter.get("/report/:runId", async (req, res) => {
  const runId = req.params.runId;

  try {
    assertRunId(runId);
    const hasReport = await hasReportArtifact(config.outputsDir, runId);

    if (!hasReport) {
      return res.status(404).json(buildErrorEnvelope("NOT_FOUND", "report.pdf not found"));
    }

    return res.sendFile(reportArtifactPath(config.outputsDir, runId), {
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename="${runId}-report.pdf"`
      }
    });
  } catch {
    return res.status(400).json(buildErrorEnvelope("INVALID_INPUT", "Invalid run_id"));
  }
});
