import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import { access } from "node:fs/promises";
import path from "node:path";
import type { ResultsJson } from "@rift/contracts";
import { schemaValidators } from "./validators.js";

const RUN_ID_PATTERN = /^[A-Za-z0-9_-]+$/;

export function assertRunId(runId: string): void {
  if (!RUN_ID_PATTERN.test(runId)) {
    throw new Error("Invalid run_id format");
  }
}

export function runOutputDir(outputsRoot: string, runId: string): string {
  assertRunId(runId);
  return path.join(outputsRoot, runId);
}

export async function writeResultsArtifact(
  outputsRoot: string,
  runId: string,
  payload: ResultsJson
): Promise<string> {
  assertRunId(runId);
  if (payload.run_id !== runId) {
    throw new Error("results.json payload run_id mismatch");
  }

  if (!schemaValidators.results(payload)) {
    throw new Error("results.json validation failed");
  }

  const dir = runOutputDir(outputsRoot, runId);
  await mkdir(dir, { recursive: true });

  const finalPath = path.join(dir, "results.json");
  const tmpPath = `${finalPath}.tmp`;
  const body = JSON.stringify(payload, null, 2);

  await writeFile(tmpPath, `${body}\n`, "utf8");
  await rename(tmpPath, finalPath);
  return finalPath;
}

export async function readResultsArtifact(outputsRoot: string, runId: string): Promise<ResultsJson> {
  const filePath = path.join(runOutputDir(outputsRoot, runId), "results.json");
  const raw = await readFile(filePath, "utf8");
  const parsed = JSON.parse(raw) as unknown;

  if (!schemaValidators.results(parsed)) {
    throw new Error("Stored results.json violates contract");
  }

  return parsed;
}

export async function hasReportArtifact(outputsRoot: string, runId: string): Promise<boolean> {
  const reportPath = path.join(runOutputDir(outputsRoot, runId), "report.pdf");
  try {
    await access(reportPath, fsConstants.R_OK);
    return true;
  } catch {
    return false;
  }
}

export function reportArtifactPath(outputsRoot: string, runId: string): string {
  return path.join(runOutputDir(outputsRoot, runId), "report.pdf");
}
