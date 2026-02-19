import type { RunAgentDuplicateResponse, RunAgentResponse } from "@rift/contracts";

export type ActiveRunStatus = "queued" | "running";

export interface ActiveRunRecord {
  run_id: string;
  status: ActiveRunStatus;
  branch_name: string;
  socket_room: string;
  fingerprint: string;
  created_at: string;
  updated_at: string;
}

class InMemoryRunStore {
  private readonly activeByFingerprint = new Map<string, ActiveRunRecord>();
  private readonly activeByRunId = new Map<string, ActiveRunRecord>();

  getActiveByFingerprint(fingerprint: string): ActiveRunRecord | undefined {
    return this.activeByFingerprint.get(fingerprint);
  }

  getActiveByRunId(runId: string): ActiveRunRecord | undefined {
    return this.activeByRunId.get(runId);
  }

  registerQueuedRun(response: RunAgentResponse): ActiveRunRecord {
    const now = new Date().toISOString();
    const record: ActiveRunRecord = {
      run_id: response.run_id,
      status: "queued",
      branch_name: response.branch_name,
      socket_room: response.socket_room,
      fingerprint: response.fingerprint,
      created_at: now,
      updated_at: now
    };

    this.activeByFingerprint.set(record.fingerprint, record);
    this.activeByRunId.set(record.run_id, record);
    return record;
  }

  markRunning(runId: string): void {
    const record = this.activeByRunId.get(runId);
    if (!record) {
      return;
    }

    record.status = "running";
    record.updated_at = new Date().toISOString();
  }

  markComplete(runId: string): void {
    const record = this.activeByRunId.get(runId);
    if (!record) {
      return;
    }

    this.activeByRunId.delete(runId);
    this.activeByFingerprint.delete(record.fingerprint);
  }

  toDuplicateResponse(record: ActiveRunRecord): RunAgentDuplicateResponse {
    return {
      run_id: record.run_id,
      status: record.status,
      message: "Active run already exists for this submission fingerprint"
    };
  }
}

export const runStore = new InMemoryRunStore();
