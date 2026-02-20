/* ──────────────────────────────────────────────────────────
 * §11.2 — Run Summary Card
 * run_id, status, branch, team, timing, progress
 * ────────────────────────────────────────────────────────── */
import { useRunContext } from "@/context/RunContext";
import Card from "@/components/Card";
import StatusBadge from "@/components/StatusBadge";
import ProgressBar from "@/components/ProgressBar";
import { getReportUrl } from "@/lib/api";

export default function RunSummaryCard() {
  const { state } = useRunContext();
  const { runId, status, currentNode, iteration, maxIterations, progressPct, results } = state;

  const totalTime = results?.total_time_secs;
  const branchName = results?.branch_name;
  const teamName = results?.team_name;

  const isRunning = status === "running" || status === "queued";
  const isTerminal = status === "passed" || status === "failed" || status === "quarantined";

  return (
    <Card
      title="Run Summary"
      glow={isRunning ? "running" : status === "passed" ? "passed" : status === "failed" ? "failed" : null}
    >
      <div className="space-y-4">
        {/* Top row: Run ID + Status */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-xs text-[var(--color-text-muted)]">Run ID</span>
            <span className="font-mono text-xs text-[var(--color-text)] border border-black/10 px-2 py-0.5">{runId ?? "—"}</span>
          </div>
          <StatusBadge status={status} pulse={isRunning} />
        </div>

        {/* Info grid */}
        <div className="grid grid-cols-2 gap-3 text-sm">
          {branchName && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase font-mono text-[var(--color-text-muted)]">Branch</span>
              <span className="truncate text-xs">{branchName}</span>
            </div>
          )}
          {teamName && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase font-mono text-[var(--color-text-muted)]">Team</span>
              <span className="truncate text-xs">{teamName}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase font-mono text-[var(--color-text-muted)]">Step</span>
            <span className="text-xs">
              Iter {iteration}/{maxIterations}
              {currentNode ? ` · ${currentNode}` : ""}
            </span>
          </div>
          {totalTime != null && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase font-mono text-[var(--color-text-muted)]">Total</span>
              <span className="text-xs">{totalTime.toFixed(1)}s</span>
            </div>
          )}
        </div>

        {/* Progress */}
        <ProgressBar value={progressPct} />

        {/* Download Report PDF — only when run is complete */}
        {isTerminal && runId && (
          <a
            href={getReportUrl(runId)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium rounded-md
                       bg-blue-600 text-white hover:bg-blue-700 transition-colors
                       shadow-sm hover:shadow-md w-fit"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Download Report PDF
          </a>
        )}
      </div>
    </Card>
  );
}
