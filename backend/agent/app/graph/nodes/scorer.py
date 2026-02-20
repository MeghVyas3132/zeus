"""
scorer node — compute final score, write results.json, emit run_complete.

Score formula (SOURCE_OF_TRUTH §12):
  - Base: 100
  - Speed bonus: +10 if total runtime < 300s
  - Efficiency penalty: -2 × max(0, commits - 20)
  - Final: base + bonus − penalty
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from ...config import (
    OUTPUTS_DIR,
    SCORE_BASE,
    SCORE_EFFICIENCY_FREE_COMMITS,
    SCORE_EFFICIENCY_PENALTY_PER_COMMIT,
    SCORE_SPEED_BONUS,
    SCORE_SPEED_THRESHOLD_SECS,
)
from ...db import insert_trace, save_report_pdf, update_run_status
from ...events import emit_run_complete, emit_thought
from ...report import generate_report_pdf
from ..state import AgentState, ScoreBreakdown

logger = logging.getLogger("rift.node.scorer")


def _public_ci_status(status: str) -> str:
    """
    Map internal CI statuses to contract-safe public statuses.
    """
    return "failed" if status == "no_ci" else status


def _compute_score(
    total_time_secs: float,
    total_commits: int,
    total_failures: int,
    total_fixes_applied: int,
    tests_passed: bool,
) -> ScoreBreakdown:
    base = float(SCORE_BASE)

    # Speed bonus only if the agent actually did meaningful work
    speed_bonus = 0.0
    if total_fixes_applied > 0 and total_time_secs < SCORE_SPEED_THRESHOLD_SECS:
        speed_bonus = float(SCORE_SPEED_BONUS)

    efficiency_penalty = float(
        SCORE_EFFICIENCY_PENALTY_PER_COMMIT * max(0, total_commits - SCORE_EFFICIENCY_FREE_COMMITS)
    )

    # Fix-rate adjustment: scale base by success rate
    # If no failures were found at all, base stays 100.
    # If failures were found, scale base by % fixed.
    if total_failures > 0:
        fix_rate = total_fixes_applied / total_failures
        base = base * fix_rate  # e.g. 2/5 fixed → base = 40

    # Bonus for passing all tests or CI
    if tests_passed:
        base = float(SCORE_BASE)  # restore full base if tests pass
        speed_bonus = float(SCORE_SPEED_BONUS) if total_time_secs < SCORE_SPEED_THRESHOLD_SECS else 0.0

    total = base + speed_bonus - efficiency_penalty
    return ScoreBreakdown(
        base=round(base, 1),
        speed_bonus=speed_bonus,
        efficiency_penalty=efficiency_penalty,
        total=max(0.0, round(total, 1)),
    )


async def scorer(state: AgentState) -> AgentState:
    """
    Compute score, write results.json, persist to DB, emit run_complete.
    """
    run_id = state["run_id"]
    start_time = state.get("start_time", time.time())
    total_time_secs = time.time() - start_time
    total_commits = state.get("total_commits", 0)
    iteration = state.get("iteration", 1)
    fixes = state.get("fixes", [])
    ci_runs = state.get("ci_runs", [])
    test_exit_code = state.get("test_exit_code", 1)
    current_ci = state.get("current_ci_status", "failed")
    step = iteration * 10 + 9

    await emit_thought(run_id, "scorer", "Computing final score…", step)

    # Determine final status
    if current_ci == "passed" or test_exit_code == 0:
        final_status = "PASSED"
    elif state.get("quarantine_reason"):
        final_status = "QUARANTINED"
    else:
        final_status = "FAILED"

    # Count every analyzed failure record except rolled-back bookkeeping entries.
    # Skipped fixes are still unresolved failures and should impact score.
    total_failures = len([f for f in fixes if f.status != "rolled_back"])
    total_fixes_applied = len([f for f in fixes if f.status == "applied"])
    tests_passed = (final_status == "PASSED")

    score = _compute_score(
        total_time_secs, total_commits,
        total_failures, total_fixes_applied, tests_passed,
    )

    # Build results.json
    results = {
        "run_id": run_id,
        "repo_url": state["repo_url"],
        "team_name": state["team_name"],
        "leader_name": state["leader_name"],
        "branch_name": state["branch_name"],
        "final_status": final_status,
        "total_failures": total_failures,
        "total_fixes": total_fixes_applied,
        "total_time_secs": round(total_time_secs, 2),
        "score": {
            "base": score.base,
            "speed_bonus": score.speed_bonus,
            "efficiency_penalty": score.efficiency_penalty,
            "total": score.total,
        },
        "fixes": [
            {
                "file": f.file_path,
                "bug_type": f.bug_type,
                "line_number": f.line_number,
                "commit_message": f.commit_message or f"[AI-AGENT] Fix {f.bug_type}",
                "status": "FIXED" if f.status == "applied" else "FAILED",
            }
            for f in fixes
        ],
        "ci_log": [
            {
                "iteration": cr.iteration,
                "status": _public_ci_status(cr.status),
                "timestamp": cr.timestamp,
                "regression": cr.regression,
            }
            for cr in ci_runs
        ],
    }

    # Write results.json to outputs directory
    output_dir = OUTPUTS_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    logger.info("Wrote %s", results_path)

    pdf_url = f"/outputs/{run_id}/report.pdf"

    # Generate report.pdf (§6.4: generated async from final data)
    try:
        pdf_path = output_dir / "report.pdf"
        generate_report_pdf(results, pdf_path)
        # Store PDF binary in DB so gateway can serve it (Railway has no shared volumes)
        pdf_bytes = pdf_path.read_bytes()
        await save_report_pdf(run_id, pdf_bytes)
        await emit_thought(run_id, "scorer", "Generated report.pdf", step)
    except Exception:
        logger.exception("Failed to generate report.pdf for run %s", run_id)
        # Non-fatal: results.json is the primary artifact

    # Persist final state to DB
    from datetime import datetime, timezone

    await update_run_status(
        run_id,
        final_status.lower(),
        end_time=datetime.now(timezone.utc),
        total_time_secs=round(total_time_secs, 2),
        base_score=int(score.base),
        speed_bonus=int(score.speed_bonus),
        efficiency_penalty=int(score.efficiency_penalty),
        final_score=int(score.total),
        total_failures=results["total_failures"],
        total_fixes=results["total_fixes"],
        total_commits=total_commits,
        total_iterations=iteration,
        quarantine_reason=state.get("quarantine_reason"),
    )

    # Emit events
    await emit_run_complete(
        run_id,
        final_status,
        {
            "base": score.base,
            "speed_bonus": score.speed_bonus,
            "efficiency_penalty": score.efficiency_penalty,
            "total": score.total,
        },
        round(total_time_secs, 2),
        pdf_url,
    )

    await emit_thought(
        run_id, "scorer",
        f"Run complete — {final_status}, score={score.total:.0f} "
        f"(base={score.base:.0f} +speed={score.speed_bonus:.0f} -eff={score.efficiency_penalty:.0f})",
        step + 1,
    )

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="scorer",
        action_type="scoring",
        action_label=f"Final: {final_status} — score {score.total:.0f}",
        payload={
            "score": {
                "base": score.base,
                "speed_bonus": score.speed_bonus,
                "efficiency_penalty": score.efficiency_penalty,
                "total": score.total,
            },
            "total_time_secs": round(total_time_secs, 2),
        },
    )

    return {
        "score": score,
        "total_time_secs": round(total_time_secs, 2),
        "results_json_path": str(results_path),
        "pdf_url": pdf_url,
        "status": final_status.lower(),  # type: ignore[typeddict-item]
        "current_node": "scorer",
    }
