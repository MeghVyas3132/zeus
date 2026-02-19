import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import request from "supertest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ResultsJson } from "@rift/contracts";
import { writeResultsArtifact } from "../src/artifacts.js";

let outputsDir = "";
let createApp: (typeof import("../src/app.js"))["createApp"];

function validResults(runId: string): ResultsJson {
  return {
    run_id: runId,
    repo_url: "https://github.com/org/repo",
    team_name: "RIFT ORGANISERS",
    leader_name: "Saiyam Kumar",
    branch_name: "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
    final_status: "PASSED",
    total_failures: 1,
    total_fixes: 1,
    total_time_secs: 144,
    score: {
      base: 100,
      speed_bonus: 10,
      efficiency_penalty: 0,
      total: 110
    },
    fixes: [
      {
        file: "src/validator.py",
        bug_type: "SYNTAX",
        line_number: 8,
        commit_message: "[AI-AGENT] fix missing colon",
        status: "FIXED"
      }
    ],
    ci_log: [
      {
        iteration: 1,
        status: "passed",
        timestamp: "2026-02-19T10:05:12Z",
        regression: false
      }
    ]
  };
}

beforeEach(async () => {
  outputsDir = await mkdtemp(path.join(os.tmpdir(), "rift-gateway-query-"));
  process.env.OUTPUTS_DIR = outputsDir;
  vi.resetModules();
  ({ createApp } = await import("../src/app.js"));
});

afterEach(async () => {
  delete process.env.OUTPUTS_DIR;
  await rm(outputsDir, { recursive: true, force: true });
});

describe("query endpoints", () => {
  it("returns queued run status for active runs", async () => {
    const app = createApp();
    const created = await request(app).post("/run-agent").send({
      repo_url: "https://github.com/org/repo",
      team_name: "RIFT ORGANISERS",
      leader_name: "Saiyam Kumar"
    });

    const runId = created.body.run_id as string;
    const statusResponse = await request(app).get(`/agent/status/${runId}`);

    expect(statusResponse.status).toBe(200);
    expect(statusResponse.body.run_id).toBe(runId);
    expect(statusResponse.body.status).toBe("queued");
    expect(statusResponse.body.max_iterations).toBe(5);
  });

  it("serves results.json artifact from outputs directory", async () => {
    const app = createApp();
    const runId = "run_results_01";

    await writeResultsArtifact(outputsDir, runId, validResults(runId));
    const response = await request(app).get(`/results/${runId}`);

    expect(response.status).toBe(200);
    expect(response.body.run_id).toBe(runId);
    expect(response.body.final_status).toBe("PASSED");
  });

  it("returns terminal status from results artifact when run is complete", async () => {
    const app = createApp();
    const runId = "run_done_01";

    await writeResultsArtifact(outputsDir, runId, validResults(runId));
    const response = await request(app).get(`/agent/status/${runId}`);

    expect(response.status).toBe(200);
    expect(response.body.status).toBe("passed");
    expect(response.body.progress_pct).toBe(100);
  });

  it("serves report.pdf artifact when present", async () => {
    const app = createApp();
    const runId = "run_report_01";
    const runDir = path.join(outputsDir, runId);

    await mkdir(runDir, { recursive: true });
    await writeFile(path.join(runDir, "report.pdf"), "%PDF-1.4", "utf8");

    const response = await request(app).get(`/report/${runId}`);

    expect(response.status).toBe(200);
    expect(response.headers["content-type"]).toMatch(/application\/pdf/);
  });
});
