import { describe, expect, it } from "vitest";
import {
  assertNonProtectedTargetBranch,
  ensureCommitPrefix,
  normalizeBugType
} from "../src/compliance.js";

describe("compliance helpers", () => {
  it("normalizes supported bug types and aliases", () => {
    expect(normalizeBugType("syntax")).toBe("SYNTAX");
    expect(normalizeBugType("type")).toBe("TYPE_ERROR");
    expect(normalizeBugType("module")).toBe("IMPORT");
  });

  it("returns null for unknown bug type", () => {
    expect(normalizeBugType("security")).toBeNull();
  });

  it("enforces commit prefix", () => {
    expect(ensureCommitPrefix("[AI-AGENT] fix parser"))
      .toBe("[AI-AGENT] fix parser");
    expect(() => ensureCommitPrefix("fix parser")).toThrow();
  });

  it("blocks protected branches", () => {
    expect(() => assertNonProtectedTargetBranch("main")).toThrow();
    expect(() => assertNonProtectedTargetBranch("master")).toThrow();
    expect(() => assertNonProtectedTargetBranch("feature/ai-fix")).not.toThrow();
  });
});
