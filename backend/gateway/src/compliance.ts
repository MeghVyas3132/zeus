const REQUIRED_BUG_TYPES = [
  "LINTING",
  "SYNTAX",
  "LOGIC",
  "TYPE_ERROR",
  "IMPORT",
  "INDENTATION"
] as const;

export type RequiredBugType = (typeof REQUIRED_BUG_TYPES)[number];

const BUG_TYPE_ALIASES: Record<string, RequiredBugType> = {
  LINT: "LINTING",
  STYLE: "LINTING",
  FORMAT: "LINTING",
  PARSE: "SYNTAX",
  COMPILATION: "SYNTAX",
  RUNTIME: "LOGIC",
  SEMANTIC: "LOGIC",
  TYPE: "TYPE_ERROR",
  TYPES: "TYPE_ERROR",
  TYPING: "TYPE_ERROR",
  MODULE: "IMPORT",
  DEPENDENCY: "IMPORT",
  WHITESPACE: "INDENTATION",
  INDENT: "INDENTATION"
};

export function normalizeBugType(input: string): RequiredBugType | null {
  const token = input.trim().toUpperCase();
  if (!token) {
    return null;
  }

  if ((REQUIRED_BUG_TYPES as readonly string[]).includes(token)) {
    return token as RequiredBugType;
  }

  return BUG_TYPE_ALIASES[token] ?? null;
}

export function ensureCommitPrefix(message: string): string {
  const trimmed = message.trim();
  if (!trimmed) {
    throw new Error("Commit message cannot be empty");
  }

  if (!trimmed.startsWith("[AI-AGENT]")) {
    throw new Error("Commit message must start with [AI-AGENT]");
  }

  return trimmed;
}

export function assertNonProtectedTargetBranch(branchName: string): void {
  const normalized = branchName.trim().toLowerCase();
  if (normalized === "main" || normalized === "master") {
    throw new Error("Writes to protected branches are forbidden");
  }
}
