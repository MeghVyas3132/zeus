from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FeatureFlags(BaseModel):
    ENABLE_KB_LOOKUP: bool = True
    ENABLE_SPECULATIVE_BRANCHES: bool = False
    ENABLE_ADVERSARIAL_TESTS: bool = True
    ENABLE_CAUSAL_GRAPH: bool = True
    ENABLE_PROVENANCE_PASS: bool = True


class AgentStartRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=64)
    repo_url: str = Field(pattern=r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?$")
    team_name: str = Field(min_length=1, max_length=120)
    leader_name: str = Field(min_length=1, max_length=120)
    branch_name: str = Field(pattern=r"^[A-Z0-9_]+_[A-Z0-9_]+_AI_Fix$")
    max_iterations: int = Field(ge=1, le=20)
    feature_flags: FeatureFlags


class AgentStartResponse(BaseModel):
    accepted: Literal[True]
    run_id: str


class AgentStatusResponse(BaseModel):
    run_id: str
    status: Literal["queued", "running", "passed", "failed", "quarantined"]
    current_node: str
    iteration: int = Field(ge=0)


class ErrorEnvelope(BaseModel):
    error: dict
