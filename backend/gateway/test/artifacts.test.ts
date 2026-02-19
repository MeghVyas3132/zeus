import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ResultsJson } from "@rift/contracts";
import {
  hasReportArtifact,
  readResultsArtifact,
  reportArtifactPath,
  writeResultsArtifact
} from "../src/artifacts.js";

const tempDirs: string[] = [];

async function makeTempDir(): Promise<string> {
  const dir = await mkdtemp(path.join(os.tmpdir(), "rift-gateway-"));
  tempDirs.push(dir);
  return dir;
}

function validResults(runId: string): ResultsJson {
  return {
    run_id: runId,
    repo_url: "https://github.com/org/repo",
    team_name: "RIFT ORGANISERS",
    leader_name: "Saiyam Kumar",
    branch_name: "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
    final_status: "PASSED",
    total_failures: 2,
    total_fixes: 2,
    total_time_secs: 244,
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

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

describe("results artifact service", () => {
  it("writes and reads a schema-valid results.json artifact", async () => {
    const outputsRoot = await makeTempDir();
    const runId = "run_abc123";

    const filePath = await writeResultsArtifact(outputsRoot, runId, validResults(runId));
    expect(filePath.endsWith(`/run_abc123/results.json`)).toBe(true);

    const loaded = await readResultsArtifact(outputsRoot, runId);
    expect(loaded.run_id).toBe(runId);
    expect(loaded.score.total).toBe(110);
  });

  it("rejects invalid results.json payloads", async () => {
    const outputsRoot = await makeTempDir();
    const runId = "run_bad01";
    const payload = {
      ...validResults(runId),
      fixes: [
        {
          file: "src/validator.py",
          bug_type: "SYNTAX" as const,
          line_number: 8,
          commit_message: "fix missing colon",
          status: "FIXED" as const
        }
      ]
    };

    await expect(writeResultsArtifact(outputsRoot, runId, payload)).rejects.toThrow(
      "results.json validation failed"
    );
  });

  it("rejects run_id mismatch between path and payload", async () => {
    const outputsRoot = await makeTempDir();
    const payload = validResults("run_payload_01");

    await expect(writeResultsArtifact(outputsRoot, "run_path_01", payload)).rejects.toThrow(
      "results.json payload run_id mismatch"
    );
  });

  it("detects report artifact existence", async () => {
    const outputsRoot = await makeTempDir();
    const runId = "run_rep01";
    const reportPath = reportArtifactPath(outputsRoot, runId);

    expect(await hasReportArtifact(outputsRoot, runId)).toBe(false);

    await mkdir(path.dirname(reportPath), { recursive: true });
    await writeFile(reportPath, "pdf", "utf8");

    expect(await hasReportArtifact(outputsRoot, runId)).toBe(true);
  });
});
