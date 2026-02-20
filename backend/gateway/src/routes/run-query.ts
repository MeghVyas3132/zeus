import { Router, type Router as RouterType } from "express";
import { buildErrorEnvelope } from "../error-envelope.js";
import { config } from "../config.js";
import {
  assertRunId,
  hasReportArtifact,
  readResultsArtifactRaw,
  readResultsArtifact,
  reportArtifactPath
} from "../artifacts.js";
import { runStore } from "../run-store.js";
import { getPool } from "../db.js";

export const runQueryRouter: RouterType = Router();

runQueryRouter.get("/agent/status/:runId", async (req, res) => {
  const runId = req.params.runId;

  try {
    assertRunId(runId);
  } catch {
    return res.status(400).json(buildErrorEnvelope("INVALID_INPUT", "Invalid run_id"));
  }

  try {
    const results = await readResultsArtifact(config.outputsDir, runId);
    return res.status(200).json({
      run_id: results.run_id,
      status: results.final_status.toLowerCase(),
      current_node: "complete",
      iteration: Math.max(1, results.ci_log.length),
      max_iterations: config.maxIterations,
      progress_pct: 100
    });
  } catch {
    // fall through to DB lookup
  }

  // DB fallback — covers runs that completed/failed without writing results.json
  try {
    const pool = getPool();
    const { rows } = await pool.query(
      `SELECT run_id, status, total_iterations, total_fixes, total_failures,
              final_score, base_score, speed_bonus, efficiency_penalty
       FROM runs WHERE run_id = $1 LIMIT 1`,
      [runId]
    );
    if (rows.length > 0) {
      const row = rows[0];
      const isTerminal = ["passed", "failed", "quarantined"].includes(row.status);
      return res.status(200).json({
        run_id: row.run_id,
        status: row.status,
        current_node: isTerminal ? "complete" : "running",
        iteration: row.total_iterations ?? 0,
        max_iterations: config.maxIterations,
        progress_pct: isTerminal ? 100 : 50
      });
    }
  } catch {
    // DB unavailable — fall through to 404
  }

  // Last fallback: in-memory queued/running state
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

  return res.status(404).json(buildErrorEnvelope("NOT_FOUND", "Run not found"));
});

runQueryRouter.get("/results/:runId", async (req, res) => {
  const runId = req.params.runId;

  // 1️⃣ Try reading from the on-disk artifact first
  try {
    const payload = await readResultsArtifact(config.outputsDir, runId);
    return res.status(200).json(payload);
  } catch (error) {
    if (error instanceof Error && error.message.includes("Invalid run_id")) {
      return res.status(400).json(buildErrorEnvelope("INVALID_INPUT", "Invalid run_id"));
    }

    // Backward-compat: if artifact exists but fails current schema,
    // still return it instead of masking as 404.
    if (
      error instanceof Error &&
      error.message.includes("violates contract")
    ) {
      try {
        const legacyPayload = await readResultsArtifactRaw(config.outputsDir, runId);
        return res
          .status(200)
          .set("X-Results-Contract", "legacy")
          .json(legacyPayload);
      } catch {
        // fall through to DB fallback
      }
    }
  }

  // 2️⃣ DB fallback — construct results from PostgreSQL tables
  try {
    assertRunId(runId);
    const pool = getPool();

    const runRow = await pool.query(
      `SELECT run_id, repo_url, team_name, leader_name, branch_name, status,
              total_failures, total_fixes, total_time_secs,
              base_score, speed_bonus, efficiency_penalty, final_score
       FROM runs WHERE run_id = $1`, [runId]
    );
    if (runRow.rows.length === 0) {
      return res.status(404).json(buildErrorEnvelope("NOT_FOUND", "Run not found"));
    }
    const run = runRow.rows[0];

    const fixRows = await pool.query(
      `SELECT file_path, bug_type, line_number, commit_message, status
       FROM fixes WHERE run_id = $1 ORDER BY applied_at`, [runId]
    );

    const ciRows = await pool.query(
      `SELECT iteration, status, triggered_at, regression_detected
       FROM ci_events WHERE run_id = $1 ORDER BY iteration`, [runId]
    );

    const statusMap: Record<string, string> = {
      passed: "PASSED", failed: "FAILED", quarantined: "QUARANTINED",
      running: "FAILED", queued: "FAILED",
    };

    const fixStatusMap: Record<string, string> = {
      applied: "FIXED", failed: "FAILED", rolled_back: "FAILED", skipped: "FAILED",
    };

    const payload = {
      run_id: run.run_id,
      repo_url: run.repo_url,
      team_name: run.team_name,
      leader_name: run.leader_name,
      branch_name: run.branch_name,
      final_status: statusMap[run.status] ?? "FAILED",
      total_failures: run.total_failures ?? 0,
      total_fixes: run.total_fixes ?? 0,
      total_time_secs: run.total_time_secs ?? 0,
      score: {
        base: run.base_score ?? 0,
        speed_bonus: run.speed_bonus ?? 0,
        efficiency_penalty: run.efficiency_penalty ?? 0,
        total: run.final_score ?? 0,
      },
      fixes: fixRows.rows.map((f: Record<string, unknown>) => ({
        file: f.file_path as string,
        bug_type: f.bug_type as string,
        line_number: f.line_number as number,
        commit_message: (f.commit_message as string) ?? "",
        status: fixStatusMap[f.status as string] ?? "FAILED",
      })),
      ci_log: ciRows.rows.map((c: Record<string, unknown>) => ({
        iteration: c.iteration as number,
        status: c.status as string,
        timestamp: (c.triggered_at as Date)?.toISOString?.() ?? new Date().toISOString(),
        regression: (c.regression_detected as boolean) ?? false,
      })),
    };

    return res.status(200).set("X-Results-Source", "database").json(payload);
  } catch {
    return res.status(404).json(buildErrorEnvelope("NOT_FOUND", "results.json not found"));
  }
});

runQueryRouter.get("/report/:runId", async (req, res) => {
  const runId = req.params.runId;

  try {
    assertRunId(runId);

    // Try local disk first
    const hasReport = await hasReportArtifact(config.outputsDir, runId);
    if (hasReport) {
      return res.sendFile(reportArtifactPath(config.outputsDir, runId), {
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition": `attachment; filename="${runId}-report.pdf"`
        }
      });
    }

    // DB fallback — Railway has no shared volumes between services
    const pool = getPool();
    const { rows } = await pool.query(
      "SELECT report_pdf FROM runs WHERE run_id = $1 LIMIT 1",
      [runId]
    );

    if (rows.length > 0 && rows[0].report_pdf) {
      const pdfBuffer: Buffer = rows[0].report_pdf;
      res.set({
        "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename="${runId}-report.pdf"`,
        "Content-Length": String(pdfBuffer.length),
        "X-Report-Source": "database"
      });
      return res.send(pdfBuffer);
    }

    return res.status(404).json(buildErrorEnvelope("NOT_FOUND", "report.pdf not found"));
  } catch {
    return res.status(400).json(buildErrorEnvelope("INVALID_INPUT", "Invalid run_id"));
  }
});

// ── GET /replay/:runId — execution trace replay ────────────
runQueryRouter.get("/replay/:runId", async (req, res) => {
  const runId = req.params.runId;

  try {
    assertRunId(runId);
  } catch {
    return res.status(400).json(buildErrorEnvelope("INVALID_INPUT", "Invalid run_id"));
  }

  try {
    const pool = getPool();
    const result = await pool.query(
      `SELECT step_index, agent_node, action_type, action_label, payload, emitted_at
       FROM execution_traces
       WHERE run_id = (SELECT run_id FROM runs WHERE run_id::text LIKE $1 LIMIT 1)
       ORDER BY step_index ASC`,
      [`%${runId.replace("run_", "")}%`]
    );

    return res.status(200).json({
      run_id: runId,
      events: result.rows.map((row: Record<string, unknown>) => ({
        step_index: row.step_index,
        agent_node: row.agent_node,
        action_type: row.action_type,
        action_label: row.action_label,
        payload: row.payload,
        emitted_at: row.emitted_at,
      })),
    });
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("Replay query error:", err);
    return res.status(500).json(buildErrorEnvelope("INTERNAL_ERROR", "Failed to retrieve replay data"));
  }
});

// ── POST /agent/query — proxy conversational query to agent ─
runQueryRouter.post("/agent/query", async (req, res) => {
  const { run_id, question } = req.body as { run_id?: string; question?: string };

  if (!run_id || !question) {
    return res
      .status(400)
      .json(buildErrorEnvelope("INVALID_INPUT", "run_id and question are required"));
  }

  try {
    assertRunId(run_id);
  } catch {
    return res.status(400).json(buildErrorEnvelope("INVALID_INPUT", "Invalid run_id"));
  }

  try {
    const agentResp = await fetch(`${config.agentBaseUrl}/agent/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id, question }),
      signal: AbortSignal.timeout(30_000),
    });

    if (!agentResp.ok) {
      return res
        .status(agentResp.status)
        .json(buildErrorEnvelope("AGENT_ERROR", `Agent returned ${agentResp.status}`));
    }

    const data = await agentResp.json();
    return res.status(200).json(data);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("Agent query proxy error:", err);
    return res
      .status(502)
      .json(buildErrorEnvelope("AGENT_UNREACHABLE", "Could not reach agent service"));
  }
});
