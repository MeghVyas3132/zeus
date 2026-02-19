import { randomUUID } from "node:crypto";
import { Router, type Router as RouterType } from "express";
import type { RunAgentDuplicateResponse, RunAgentRequest, RunAgentResponse } from "@rift/contracts";
import { formatBranchName } from "../branch.js";
import { submissionFingerprint } from "../fingerprint.js";
import { schemaValidators, validateBody } from "../validators.js";
import { buildErrorEnvelope } from "../error-envelope.js";
import { runStore } from "../run-store.js";

export const runAgentRouter: RouterType = Router();

runAgentRouter.post("/run-agent", validateBody("runAgentRequest"), (req, res) => {
  const payload = req.body as RunAgentRequest;
  const fingerprint = submissionFingerprint(payload);
  const existing = runStore.getActiveByFingerprint(fingerprint);

  if (existing) {
    const duplicateResponse: RunAgentDuplicateResponse = runStore.toDuplicateResponse(existing);
    if (!schemaValidators.runAgentDuplicateResponse(duplicateResponse)) {
      return res
        .status(500)
        .json(buildErrorEnvelope("INTERNAL_CONTRACT_ERROR", "Generated duplicate response violates contract"));
    }

    return res.status(409).json(duplicateResponse);
  }

  let branchName: string;
  try {
    branchName = formatBranchName(payload.team_name, payload.leader_name);
  } catch {
    return res
      .status(400)
      .json(buildErrorEnvelope("INVALID_INPUT", "Unable to compute valid branch name"));
  }

  const runId = `run_${randomUUID().replace(/-/g, "").slice(0, 12)}`;
  const response: RunAgentResponse = {
    run_id: runId,
    branch_name: branchName,
    status: "queued",
    socket_room: `/run/${runId}`,
    fingerprint
  };

  if (!schemaValidators.runAgentResponse(response)) {
    return res
      .status(500)
      .json(buildErrorEnvelope("INTERNAL_CONTRACT_ERROR", "Generated response violates contract"));
  }

  runStore.registerQueuedRun(response);
  return res.status(202).json(response);
});
