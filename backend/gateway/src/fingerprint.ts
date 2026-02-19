import { createHash } from "node:crypto";

export function submissionFingerprint(input: {
  repo_url: string;
  team_name: string;
  leader_name: string;
  requested_ref?: string;
}): string {
  const raw = `${input.repo_url}|${input.team_name}|${input.leader_name}|${input.requested_ref ?? "main"}`;
  return createHash("sha256").update(raw).digest("hex");
}
