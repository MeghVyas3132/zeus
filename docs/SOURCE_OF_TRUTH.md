# SOURCE OF TRUTH

This file is the canonical contract for the RIFT 2026 Autonomous CI/CD Healing Agent.
All other docs must conform to this file.

## 1) Mission and Scope

Goal: autonomously heal CI/CD failures for a submitted GitHub repository while satisfying the hackathon track requirements.

Must-do outcomes per run:
1. Accept input: `repo_url`, `team_name`, `leader_name`.
2. Create compliant branch name.
3. Detect failing tests and classify required bug types.
4. Generate and validate fixes.
5. Commit fixes with required prefix.
6. Push branch.
7. Monitor CI and iterate up to retry limit.
8. Produce `results.json`.
9. Expose final state in dashboard.

## 2) Non-Negotiable Compliance Rules

1. Branch name must follow exact format:
`TEAM_NAME_LEADER_NAME_AI_Fix`

Algorithm:
- Normalize `team_name` and `leader_name` to uppercase.
- Replace spaces with `_`.
- Remove non-alphanumeric characters except `_`.
- Concatenate with `_AI_Fix` suffix (literal case as shown).

2. Commit message must start with `[AI-AGENT]`.

3. Never push to `main` or `master`.

4. No hardcoded test file paths.

5. No human intervention during run execution.

6. Retry limit default is `5` and must be configurable.

7. Dashboard must include required sections from track rubric.

## 3) Required Bug Types for Scoring

The required visible bug types in the primary fixes table are:
- `LINTING`
- `SYNTAX`
- `LOGIC`
- `TYPE_ERROR`
- `IMPORT`
- `INDENTATION`

Optional extended types are allowed for internal intelligence, but the primary scoring table must remain compatible with required types.

## 4) System Architecture

Layers:
1. Frontend: React dashboard.
2. API Gateway: Node.js + Express + Socket.io.
3. Queue: BullMQ + Redis.
4. Agent Service: FastAPI + LangGraph.
5. Execution Sandbox: Docker per language.
6. Storage: PostgreSQL + Redis + filesystem (+ optional vector store).

## 5) Canonical API Contracts

Public endpoints:
- `POST /run-agent`
- `GET /results/:runId`
- `GET /replay/:runId`
- `GET /report/:runId`
- `GET /agent/status/:runId`
- `POST /agent/query`
- `GET /health`

Internal endpoints:
- `POST /agent/start`
- `GET /agent/status`
- `GET /agent/stream`
- `POST /agent/query`

Socket room and events:
- Room: `/run/:runId`
- Events:
  - `thought_event`
  - `fix_applied`
  - `ci_update`
  - `telemetry_tick`
  - `run_complete`

## 6) Canonical Data Contracts

### 6.1 PostgreSQL

Core tables:
- `runs`
- `fixes`
- `ci_events`
- `execution_traces`
- `strategy_weights`
- `benchmark_scores`

Canonical status values:
- run: `queued | running | passed | failed | quarantined`
- fix: `applied | failed | rolled_back | skipped`
- ci: `pending | running | passed | failed`

### 6.2 Confidence Scale

Canonical rule:
- Storage: float in range `[0.0, 1.0]`.
- Display: percentage `[0, 100]`.

### 6.3 Redis

Use Redis for:
- BullMQ queue state.
- Live run cache.
- Event buffer.
- Session and rate limit keys.

### 6.4 Filesystem Artifacts

Per run output dir:
- `/outputs/{run_id}/results.json`
- `/outputs/{run_id}/report.pdf`

Write order:
1. Write `results.json` at terminal run state.
2. Generate `report.pdf` async from final data.

## 7) Determinism and Accuracy Policy

To maximize test-case match accuracy:
1. Rule-based parser/classifier for known failures first.
2. LLM fallback only when rule path cannot resolve.
3. Normalize file paths, line numbers, and bug-type labels before persistence.
4. Require schema validation before emitting UI payloads.
5. Golden tests for exact expected formatting.

## 8) Idempotency and Duplicate Submission Policy

Duplicate prevention is based on submission fingerprint, not run id.

Fingerprint:
`sha256(repo_url + team_name + leader_name + requested_ref)`

Behavior:
- If active run exists for same fingerprint, return existing `run_id`.
- If completed run exists and rerun not requested, optionally return cached result.

## 9) Security Baseline

1. Sandbox containers run with no outbound network by default (`--network none`).
2. Containers are short-lived and isolated per run.
3. Secrets redaction before logging and before vector indexing.
4. Protected branch writes blocked at gateway and agent layers.
5. Optional policy engine for sensitive file paths.

## 10) Advanced Features Policy

Advanced features must be behind feature flags and must not break required scoring output.

Recommended flags:
- `ENABLE_SPECULATIVE_BRANCHES`
- `ENABLE_ADVERSARIAL_TESTS`
- `ENABLE_CAUSAL_GRAPH`
- `ENABLE_PROVENANCE_PASS` 
- `ENABLE_KB_LOOKUP`

## 11) Dashboard Required Sections (Judge View)

Required sections:
1. Input Section
2. Run Summary Card
3. Score Breakdown Panel
4. Fixes Applied Table
5. CI/CD Status Timeline

Additional sections are optional and should not obscure required sections.

## 12) Score Formula

- Base: `100`
- Speed bonus: `+10` if total runtime `< 300s`
- Efficiency penalty: `-2 * max(0, commits - 20)`
- Final: `base + bonus - penalty`

## 13) results.json Canonical Shape

Required fields:
- `run_id`
- `repo_url`
- `team_name`
- `leader_name`
- `branch_name`
- `final_status`
- `total_failures`
- `total_fixes`
- `total_time_secs`
- `score: { base, speed_bonus, efficiency_penalty, total }`
- `fixes[]`
- `ci_log[]`

## 14) Document Governance

When any contract changes:
1. Update this file first.
2. Update all dependent docs in this directory.
3. Run consistency checks and contract tests.
4. Treat mismatches as blocking defects.
