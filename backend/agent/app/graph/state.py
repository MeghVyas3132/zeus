"""
Canonical LangGraph agent state.

Every node reads / writes fields in this TypedDict.  LangGraph merges
the partial dict returned by each node back into the overall state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

BugType = Literal[
    "LINTING", "SYNTAX", "LOGIC", "TYPE_ERROR", "IMPORT", "INDENTATION"
]

FixStatus = Literal["applied", "failed", "rolled_back", "skipped"]
CiStatus = Literal["pending", "running", "passed", "failed", "no_ci"]
RunStatus = Literal["queued", "running", "passed", "failed", "quarantined"]


# ── Structured sub-records ──────────────────────────────────
@dataclass
class TestFailure:
    """A single test failure parsed from test output."""
    file_path: str
    test_name: str
    line_number: int
    error_message: str
    bug_type: BugType
    raw_output: str = ""


@dataclass
class FixRecord:
    """A fix applied (or attempted) to a single failure."""
    file_path: str
    bug_type: BugType
    line_number: int
    description: str
    fix_description: str
    original_code: str
    fixed_code: str
    status: FixStatus = "applied"
    commit_sha: str | None = None
    commit_message: str = ""
    confidence: float = 0.0
    model_used: str = "rule-based"


@dataclass
class CiRun:
    """One CI iteration result."""
    iteration: int
    status: CiStatus = "pending"
    github_run_id: int | None = None
    failures_before: int = 0
    failures_after: int = 0
    regression: bool = False
    rollback_triggered: bool = False
    rollback_commit_sha: str | None = None
    duration_secs: float = 0.0
    timestamp: str = ""


@dataclass
class ScoreBreakdown:
    base: float = 100.0
    speed_bonus: float = 0.0
    efficiency_penalty: float = 0.0
    total: float = 100.0


# ── The main LangGraph state ───────────────────────────────
class AgentState(TypedDict, total=False):
    """
    Every field is optional (total=False) so nodes only return the
    keys they want to update. LangGraph merges partials automatically.
    """

    # ── Identity ──────────────────────────────────────
    run_id: str
    repo_url: str
    team_name: str
    leader_name: str
    branch_name: str
    max_iterations: int
    feature_flags: dict[str, bool]

    # ── Repo scanning ─────────────────────────────────
    repo_dir: str               # local clone path
    language: str               # "python", "javascript", "typescript", etc.
    framework: str              # "pytest", "jest", "mocha", etc.
    test_files: list[str]       # paths relative to repo root

    # ── Test running / analysis ───────────────────────
    test_output: str            # raw stdout+stderr from test runner
    test_exit_code: int
    failures: list[TestFailure]

    # ── Fix generation ────────────────────────────────
    fixes: list[FixRecord]
    total_commits: int
    pushed_this_iteration: bool

    # ── CI monitoring ─────────────────────────────────
    ci_runs: list[CiRun]
    current_ci_status: CiStatus
    regression_detected: bool
    ci_workflow_created: bool    # True after ci_workflow_creator pushes a workflow

    # ── Iteration control ─────────────────────────────
    iteration: int
    current_node: str
    status: RunStatus

    # ── Scoring ───────────────────────────────────────
    score: ScoreBreakdown
    total_time_secs: float
    start_time: float           # time.time() at run start

    # ── Outputs ───────────────────────────────────────
    results_json_path: str
    pdf_url: str

    # ── Error / quarantine ────────────────────────────
    error_message: str
    quarantine_reason: str
