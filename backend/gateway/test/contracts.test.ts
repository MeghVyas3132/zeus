import { describe, expect, it } from "vitest";
import { schemaValidators } from "../src/validators.js";

describe("contract schema validators", () => {
  it("accepts canonical thought_event payload", () => {
    const payload = {
      run_id: "run_abc123",
      node: "fix_generator",
      message: "Rule path failed, switching to model route",
      step_index: 92,
      timestamp: "2026-02-19T10:03:02Z"
    };

    expect(schemaValidators.thoughtEvent(payload)).toBe(true);
  });

  it("accepts canonical fix_applied payload", () => {
    const payload = {
      run_id: "run_abc123",
      file: "src/validator.py",
      bug_type: "SYNTAX",
      line: 8,
      status: "applied",
      confidence: 0.91,
      commit_sha: "abc123def"
    };

    expect(schemaValidators.fixAppliedEvent(payload)).toBe(true);
  });

  it("accepts canonical ci_update payload", () => {
    const payload = {
      run_id: "run_abc123",
      iteration: 2,
      status: "failed",
      regression: true,
      timestamp: "2026-02-19T10:05:12Z"
    };

    expect(schemaValidators.ciUpdateEvent(payload)).toBe(true);
  });

  it("accepts canonical telemetry_tick payload", () => {
    const payload = {
      run_id: "run_abc123",
      container_id: "c1",
      cpu_pct: 42.3,
      mem_mb: 312,
      timestamp: "2026-02-19T10:05:13Z"
    };

    expect(schemaValidators.telemetryTickEvent(payload)).toBe(true);
  });

  it("accepts canonical run_complete payload", () => {
    const payload = {
      run_id: "run_abc123",
      final_status: "PASSED",
      score: {
        base: 100,
        speed_bonus: 10,
        efficiency_penalty: 0,
        total: 110
      },
      total_time_secs: 244,
      pdf_url: "/report/run_abc123"
    };

    expect(schemaValidators.runCompleteEvent(payload)).toBe(true);
  });

  it("accepts canonical results.json payload", () => {
    const payload = {
      run_id: "run_abc123",
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

    expect(schemaValidators.results(payload)).toBe(true);
  });

  it("rejects invalid fix_applied confidence out of range", () => {
    const payload = {
      run_id: "run_abc123",
      file: "src/validator.py",
      bug_type: "SYNTAX",
      line: 8,
      status: "applied",
      confidence: 1.2,
      commit_sha: "abc123def"
    };

    expect(schemaValidators.fixAppliedEvent(payload)).toBe(false);
  });

  it("rejects invalid run-agent response branch format", () => {
    const payload = {
      run_id: "run_abc123",
      branch_name: "rift_bad_branch",
      status: "queued",
      socket_room: "/run/run_abc123",
      fingerprint: "3dc49b0aa7a4648ceee63780f2d0b1477f0f5b8cd86d5914fa66f4ec9baf1910"
    };

    expect(schemaValidators.runAgentResponse(payload)).toBe(false);
  });

  it("accepts duplicate run-agent response payload", () => {
    const payload = {
      run_id: "run_abc123",
      status: "running",
      message: "Active run already exists for this submission fingerprint"
    };

    expect(schemaValidators.runAgentDuplicateResponse(payload)).toBe(true);
  });
});
