import { describe, expect, it, vi } from "vitest";
import { ContractSafeBroadcaster } from "../src/socket-broadcaster.js";

describe("ContractSafeBroadcaster", () => {
  it("emits validated payloads to room", () => {
    const emit = vi.fn();
    const io = {
      to: vi.fn().mockReturnValue({ emit })
    };

    const broadcaster = new ContractSafeBroadcaster(io);
    broadcaster.emitThought("/run/run_123", {
      run_id: "run_123",
      node: "repo_scanner",
      message: "scan started",
      step_index: 1,
      timestamp: "2026-02-19T10:00:00Z"
    });

    expect(io.to).toHaveBeenCalledWith("/run/run_123");
    expect(emit).toHaveBeenCalledWith("thought_event", expect.any(Object));
  });

  it("throws for invalid payload", () => {
    const io = {
      to: vi.fn().mockReturnValue({ emit: vi.fn() })
    };

    const broadcaster = new ContractSafeBroadcaster(io);

    expect(() =>
      broadcaster.emitFixApplied("/run/run_123", {
        run_id: "run_123",
        file: "src/app.ts",
        bug_type: "SYNTAX",
        line: 1,
        status: "applied",
        confidence: 2,
        commit_sha: "abcdef1"
      })
    ).toThrow("Invalid fix_applied payload");
  });
});
