from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


BugType = Literal["LINTING", "SYNTAX", "LOGIC", "TYPE_ERROR", "IMPORT", "INDENTATION"]
CiStatus = Literal["pending", "running", "passed", "failed"]


class ErrorDetailEnvelope(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetailEnvelope


class RunAgentRequest(BaseModel):
    repo_url: str = Field(pattern=r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?$")
    team_name: str = Field(min_length=1, max_length=120)
    leader_name: str = Field(min_length=1, max_length=120)
    requested_ref: str | None = Field(default=None, min_length=1, max_length=120)


class RunAgentResponse(BaseModel):
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    branch_name: str = Field(pattern=r"^[A-Z0-9_]+_[A-Z0-9_]+_AI_Fix$")
    status: Literal["queued"]
    socket_room: str = Field(pattern=r"^/run/[A-Za-z0-9_-]+$")
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class ScoreBreakdown(BaseModel):
    base: float
    speed_bonus: float
    efficiency_penalty: float
    total: float


class ResultFixRow(BaseModel):
    file: str
    bug_type: BugType
    line_number: int = Field(ge=1)
    commit_message: str = Field(pattern=r"^\[AI-AGENT\].+")
    status: Literal["FIXED", "FAILED"]


class ResultCiRow(BaseModel):
    iteration: int = Field(ge=1)
    status: CiStatus
    timestamp: str
    regression: bool


class ResultsJson(BaseModel):
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    repo_url: str = Field(pattern=r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?$")
    team_name: str = Field(min_length=1, max_length=120)
    leader_name: str = Field(min_length=1, max_length=120)
    branch_name: str = Field(pattern=r"^[A-Z0-9_]+_[A-Z0-9_]+_AI_Fix$")
    final_status: Literal["PASSED", "FAILED", "QUARANTINED"]
    total_failures: int = Field(ge=0)
    total_fixes: int = Field(ge=0)
    total_time_secs: float = Field(ge=0)
    score: ScoreBreakdown
    fixes: list[ResultFixRow]
    ci_log: list[ResultCiRow]


class ThoughtEvent(BaseModel):
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    node: str
    message: str
    step_index: int = Field(ge=1)
    timestamp: str


class FixAppliedEvent(BaseModel):
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    file: str
    bug_type: BugType
    line: int = Field(ge=1)
    status: Literal["applied", "failed", "rolled_back", "skipped"]
    confidence: float = Field(ge=0.0, le=1.0)
    commit_sha: str | None = Field(default=None, pattern=r"^[a-f0-9]{7,40}$")


class CiUpdateEvent(BaseModel):
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    iteration: int = Field(ge=1)
    status: CiStatus
    regression: bool
    timestamp: str


class TelemetryTickEvent(BaseModel):
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    container_id: str
    cpu_pct: float = Field(ge=0)
    mem_mb: float = Field(ge=0)
    timestamp: str


class RunCompleteEvent(BaseModel):
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    final_status: Literal["PASSED", "FAILED", "QUARANTINED"]
    score: ScoreBreakdown
    total_time_secs: float = Field(ge=0)
    pdf_url: str
