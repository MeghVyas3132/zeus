"""
Async PostgreSQL persistence layer.

Uses asyncpg for connection pooling and prepared-statement performance.
All writes go through thin helpers that match the canonical SCHEMA.sql.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import uuid4

import asyncpg

from .config import DATABASE_URL

logger = logging.getLogger("rift.db")

_pool: asyncpg.Pool | None = None


# ── Pool management ─────────────────────────────────────────

async def get_pool() -> asyncpg.Pool:
    """Return (or create) a connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL.replace("postgres://", "postgresql://"),
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
    assert _pool is not None
    return _pool


async def close_pool() -> None:
    """Gracefully close the pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ── Runs ────────────────────────────────────────────────────

async def update_run_status(
    run_id: str,
    status: str,
    *,
    end_time: datetime | None = None,
    total_time_secs: float | None = None,
    base_score: int | None = None,
    speed_bonus: int | None = None,
    efficiency_penalty: int | None = None,
    final_score: int | None = None,
    total_failures: int | None = None,
    total_fixes: int | None = None,
    total_commits: int | None = None,
    total_iterations: int | None = None,
    quarantine_reason: str | None = None,
) -> None:
    """Update run row with status and optional terminal fields."""
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE runs
           SET status            = $2,
               end_time          = COALESCE($3,  end_time),
               total_time_secs   = COALESCE($4,  total_time_secs),
               base_score        = COALESCE($5,  base_score),
               speed_bonus       = COALESCE($6,  speed_bonus),
               efficiency_penalty= COALESCE($7,  efficiency_penalty),
               final_score       = COALESCE($8,  final_score),
               total_failures    = COALESCE($9,  total_failures),
               total_fixes       = COALESCE($10, total_fixes),
               total_commits     = COALESCE($11, total_commits),
               total_iterations  = COALESCE($12, total_iterations),
               quarantine_reason = COALESCE($13, quarantine_reason)
         WHERE run_id = $1
        """,
        run_id,
        status,
        end_time,
        total_time_secs,
        base_score,
        speed_bonus,
        efficiency_penalty,
        final_score,
        total_failures,
        total_fixes,
        total_commits,
        total_iterations,
        quarantine_reason,
    )
    logger.debug("update_run_status run=%s status=%s", run_id, status)


# ── Fixes ───────────────────────────────────────────────────

async def insert_fix(
    run_id: str,
    *,
    file_path: str,
    bug_type: str,
    line_number: int,
    description: str,
    fix_description: str,
    original_code: str,
    fixed_code: str,
    status: str,
    commit_sha: str | None = None,
    commit_message: str | None = None,
    confidence_score: float = 0.0,
    model_used: str = "rule-based",
) -> str:
    """Insert a fix row and return the fix_id."""
    # Sanitize bug_type to match DB CHECK constraint
    _VALID = {"LINTING", "SYNTAX", "LOGIC", "TYPE_ERROR", "IMPORT", "INDENTATION"}
    if bug_type not in _VALID:
        bug_type = "LOGIC"

    fix_id = str(uuid4())
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO fixes (
            fix_id, run_id, file_path, bug_type, line_number,
            description, fix_description, original_code, fixed_code,
            status, commit_sha, commit_message, confidence_score, model_used
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10, $11, $12, $13, $14
        )
        """,
        fix_id,
        run_id,
        file_path,
        bug_type,
        line_number,
        description,
        fix_description,
        original_code,
        fixed_code,
        status,
        commit_sha,
        commit_message,
        confidence_score,
        model_used,
    )
    logger.debug("insert_fix run=%s fix=%s file=%s", run_id, fix_id, file_path)
    return fix_id


# ── CI Events ───────────────────────────────────────────────

async def insert_ci_event(
    run_id: str,
    *,
    iteration: int,
    status: str,
    github_run_id: int | None = None,
    failures_before: int = 0,
    failures_after: int = 0,
    regression_detected: bool = False,
    rollback_triggered: bool = False,
    rollback_commit_sha: str | None = None,
    duration_secs: float = 0.0,
    triggered_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> str:
    """Insert a CI event row."""
    event_id = str(uuid4())
    now = datetime.now(timezone.utc)
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO ci_events (
            event_id, run_id, iteration, status,
            github_run_id, failures_before, failures_after,
            regression_detected, rollback_triggered, rollback_commit_sha,
            duration_secs, triggered_at, completed_at
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6, $7,
            $8, $9, $10,
            $11, $12, $13
        )
        """,
        event_id,
        run_id,
        iteration,
        status,
        github_run_id,
        failures_before,
        failures_after,
        regression_detected,
        rollback_triggered,
        rollback_commit_sha,
        duration_secs,
        triggered_at or now,
        completed_at,
    )
    return event_id


# ── Execution Traces ────────────────────────────────────────

async def insert_trace(
    run_id: str,
    *,
    step_index: int,
    agent_node: str,
    action_type: str,
    action_label: str,
    payload: dict[str, Any] | None = None,
    thought_text: str | None = None,
    related_fix_id: str | None = None,
    related_ci_event_id: str | None = None,
) -> str:
    """Insert an execution trace row."""
    trace_id = str(uuid4())
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO execution_traces (
            trace_id, run_id, step_index, agent_node,
            action_type, action_label, payload, thought_text,
            related_fix_id, related_ci_event_id
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6, $7::jsonb, $8,
            $9, $10
        )
        """,
        trace_id,
        run_id,
        step_index,
        agent_node,
        action_type,
        action_label,
        json.dumps(payload) if payload else None,
        thought_text,
        related_fix_id,
        related_ci_event_id,
    )
    return trace_id


# ── Query helpers ───────────────────────────────────────────

async def get_run(run_id: str) -> dict[str, Any] | None:
    """Fetch a single run by ID."""
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM runs WHERE run_id = $1", run_id)
    return dict(row) if row else None


async def get_fixes_for_run(run_id: str) -> list[dict[str, Any]]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM fixes WHERE run_id = $1 ORDER BY applied_at",
        run_id,
    )
    return [dict(r) for r in rows]


async def get_ci_events_for_run(run_id: str) -> list[dict[str, Any]]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM ci_events WHERE run_id = $1 ORDER BY iteration",
        run_id,
    )
    return [dict(r) for r in rows]


async def get_traces_for_run(run_id: str) -> list[dict[str, Any]]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM execution_traces WHERE run_id = $1 ORDER BY step_index",
        run_id,
    )
    return [dict(r) for r in rows]


async def save_report_pdf(run_id: str, pdf_bytes: bytes) -> None:
    """Store the generated report PDF binary in the runs table."""
    pool = await get_pool()
    await pool.execute(
        "UPDATE runs SET report_pdf = $2 WHERE run_id = $1",
        run_id,
        pdf_bytes,
    )
    logger.info("Saved report_pdf (%d bytes) for run %s", len(pdf_bytes), run_id)
