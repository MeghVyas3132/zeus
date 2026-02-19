export type RunStatus = "queued" | "running" | "passed" | "failed" | "quarantined";

export interface RunAgentRequest {
  repo_url: string;
  team_name: string;
  leader_name: string;
  requested_ref?: string;
}

export interface RunAgentResponse {
  run_id: string;
  branch_name: string;
  status: "queued";
  socket_room: string;
  fingerprint: string;
}

export interface RunAgentDuplicateResponse {
  run_id: string;
  status: "queued" | "running";
  message: string;
}

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface ScoreBreakdown {
  base: number;
  speed_bonus: number;
  efficiency_penalty: number;
  total: number;
}

export interface ResultFixRow {
  file: string;
  bug_type: "LINTING" | "SYNTAX" | "LOGIC" | "TYPE_ERROR" | "IMPORT" | "INDENTATION";
  line_number: number;
  commit_message: string;
  status: "FIXED" | "FAILED";
}

export interface ResultCiRow {
  iteration: number;
  status: "passed" | "failed" | "running" | "pending";
  timestamp: string;
  regression: boolean;
}

export interface ResultsJson {
  run_id: string;
  repo_url: string;
  team_name: string;
  leader_name: string;
  branch_name: string;
  final_status: "PASSED" | "FAILED" | "QUARANTINED";
  total_failures: number;
  total_fixes: number;
  total_time_secs: number;
  score: ScoreBreakdown;
  fixes: ResultFixRow[];
  ci_log: ResultCiRow[];
}

export interface ThoughtEvent {
  run_id: string;
  node: string;
  message: string;
  step_index: number;
  timestamp: string;
}

export interface FixAppliedEvent {
  run_id: string;
  file: string;
  bug_type: ResultFixRow["bug_type"];
  line: number;
  status: "applied" | "failed" | "rolled_back" | "skipped";
  confidence: number;
  commit_sha?: string;
}

export interface CiUpdateEvent {
  run_id: string;
  iteration: number;
  status: "passed" | "failed" | "running" | "pending";
  regression: boolean;
  timestamp: string;
}

export interface TelemetryTickEvent {
  run_id: string;
  container_id: string;
  cpu_pct: number;
  mem_mb: number;
  timestamp: string;
}

export interface RunCompleteEvent {
  run_id: string;
  final_status: ResultsJson["final_status"];
  score: ScoreBreakdown;
  total_time_secs: number;
  pdf_url: string;
}
