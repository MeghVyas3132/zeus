# Copilot Build Guide

This guide is written so GitHub Copilot can implement the system end-to-end with low ambiguity.

Canonical contract order:
1. `SOURCE_OF_TRUTH.md`
2. `API_CONTRACTS.md`
3. `db-architecture.txt` + `SCHEMA.sql`
4. `architecture.txt`
5. `user-flow.txt`

## 1) Monorepo Structure (Recommended)

```text
/
  frontend/
  backend/
    gateway/
    worker/
    agent/
  packages/
    contracts/
  outputs/
  README.md
  SOURCE_OF_TRUTH.md
  API_CONTRACTS.md
  SCHEMA.sql
```

## 2) Build Sequence

## Phase A: Contracts and Types (Do first)

Tasks:
1. Create shared TypeScript/Python contracts from `API_CONTRACTS.md`.
2. Add JSON schema for:
   - run-agent request/response
   - results.json
   - socket events
3. Add validators in gateway and agent.

Acceptance:
- invalid payload returns standard error envelope.
- all event payloads pass schema tests.

## Phase B: Gateway and Queue

Tasks:
1. Implement `POST /run-agent` with strict validation.
2. Implement branch formatter function.
3. Implement dedupe by fingerprint.
4. Enqueue BullMQ jobs.
5. Implement artifact endpoints:
   - `GET /results/:runId`
   - `GET /report/:runId`
6. Implement socket room broadcast helper.

Acceptance:
- branch formatter unit tests pass.
- duplicate submission returns existing run while active.
- run-agent returns room `/run/:runId`.

## Phase C: Agent Service and Graph

Tasks:
1. Create FastAPI service with `/agent/start`, `/agent/status`, `/agent/stream`.
2. Implement LangGraph nodes in canonical order.
3. Implement retry loops and regression rollback path.
4. Persist run/fix/ci/trace events.

Acceptance:
- graph executes to terminal state with mocked adapters.
- retry stops exactly at configured max.
- trace ordering is monotonic by `step_index`.

## Phase D: Sandbox Runner

Tasks:
1. Build Docker runner abstraction with:
   - network disabled
   - timeouts
   - resource limits
2. Add language command adapters (python/node first).
3. Parse test output to normalized failure model.

Acceptance:
- sandbox smoke test passes.
- timeout and kill behavior validated.
- parser returns deterministic line/bug data for fixtures.

## Phase E: Fix Engine

Tasks:
1. Rule-first bug classifier and patch templates.
2. LLM fallback interface.
3. Critic validation + confidence scoring.
4. Commit optimizer with prefix enforcement.

Acceptance:
- required bug types map correctly.
- confidence stored in [0.0,1.0].
- commit prefix check blocks invalid messages.

## Phase F: CI Monitor and Rollback

Tasks:
1. GitHub Actions poller with backoff.
2. Regression detector comparing previous vs current failing tests.
3. Rollback agent issuing targeted revert.

Acceptance:
- simulated regression triggers rollback path.
- failed-with-retries loops until max.

## Phase G: Frontend Dashboard

Tasks:
1. Build required sections first:
   - input
   - summary
   - score
   - fixes table
   - CI timeline
2. Add websocket client and state store.
3. Add loading and terminal states.

Acceptance:
- dashboard receives all required events.
- responsive layout on desktop/mobile.
- required fields visible and correct.

## Phase H: Optional Advanced Features

Tasks:
1. Causal incident graph panel.
2. Provenance panel.
3. Replay timeline.
4. optional branch tournament.

Acceptance:
- all advanced features behind flags.
- disabling flags does not break core flow.

## 3) Copilot Prompt Templates

## 3.1 Branch Formatter
Prompt:
"Implement a pure function `format_branch_name(team_name, leader_name)` that returns exact format `TEAM_NAME_LEADER_NAME_AI_Fix` with normalization rules from SOURCE_OF_TRUTH.md. Add exhaustive unit tests."

## 3.2 run-agent Handler
Prompt:
"Generate Express route `POST /run-agent` with JSON schema validation, dedupe-by-fingerprint, BullMQ enqueue, and response shape from API_CONTRACTS.md."

## 3.3 Results Schema Validator
Prompt:
"Create JSON schema and validation function for results.json exactly matching SOURCE_OF_TRUTH.md and fail write if schema invalid."

## 3.4 Socket Event Broadcaster
Prompt:
"Implement strongly typed socket event broadcaster for events `thought_event`, `fix_applied`, `ci_update`, `telemetry_tick`, `run_complete` with payload contracts from API_CONTRACTS.md."

## 3.5 Retry State Machine
Prompt:
"Implement deterministic retry state machine with states running/passed/failed/quarantined and transitions from user-flow.txt. Include regression rollback transition."

## 4) Test Strategy for Copilot Implementation

Minimum automated tests:
1. Unit tests
   - branch formatter
   - bug type normalizer
   - score calculator
   - confidence scale converter
2. Contract tests
   - all REST payloads
   - socket payload schemas
3. Integration tests
   - run creation -> queue -> agent start
   - fix loop -> CI loop -> completion
4. Golden tests
   - required output format for test-case examples
5. E2E tests
   - dashboard renders required sections and updates live

## 5) Common Implementation Pitfalls

1. Storing confidence as percent instead of [0.0,1.0].
2. Missing `/report/:runId` endpoint.
3. Dedupe by run_id instead of fingerprint.
4. Mixed bug taxonomy in required fixes table.
5. Non-prefixed commit messages.

## 6) Definition of Done

A run is done only when:
1. run terminal status is persisted.
2. results.json written and schema-valid.
3. run_complete emitted.
4. required dashboard sections display final values.

## 7) Fast Validation Commands (suggested)

```bash
# type checks
npm run typecheck

# backend tests
npm run test:gateway
pytest -q

# contract tests
npm run test:contracts

# e2e smoke
npm run test:e2e
```

## 8) Final Demo Readiness Checklist

1. Live URL accessible from incognito window.
2. Submit known failing repo and show autonomous loop.
3. Show branch name and commit prefix compliance.
4. Show final score panel and CI timeline.
5. Download and open results/report artifacts.
