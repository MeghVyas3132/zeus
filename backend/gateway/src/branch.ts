function normalizeToken(input: string): string {
  return input
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "_")
    .replace(/[^A-Z0-9_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export function formatBranchName(teamName: string, leaderName: string): string {
  const team = normalizeToken(teamName);
  const leader = normalizeToken(leaderName);

  if (!team || !leader) {
    throw new Error("Invalid team_name or leader_name for branch formatting");
  }

  return `${team}_${leader}_AI_Fix`;
}
