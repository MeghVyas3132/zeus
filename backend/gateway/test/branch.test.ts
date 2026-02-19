import { describe, expect, it } from "vitest";
import { formatBranchName } from "../src/branch.js";

describe("formatBranchName", () => {
  it("formats canonical sample correctly", () => {
    expect(formatBranchName("RIFT ORGANISERS", "Saiyam Kumar")).toBe(
      "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix"
    );
  });

  it("strips unsupported characters and normalizes spaces", () => {
    expect(formatBranchName("Code   Warriors!", "John.Doe")).toBe(
      "CODE_WARRIORS_JOHNDOE_AI_Fix"
    );
  });

  it("throws on empty normalized inputs", () => {
    expect(() => formatBranchName("***", "$$$")).toThrow();
  });
});
