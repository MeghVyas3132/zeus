# Implementation Tasks

This is a build board aligned to the track and scoring rubric.

## Epic 1: Compliance Core (highest priority)

1. Implement strict branch formatter.
2. Enforce `[AI-AGENT]` commit prefix.
3. Protect `main/master` from automated writes.
4. Implement required bug type taxonomy in primary table.
5. Implement `results.json` schema and writer.

Acceptance:
- all compliance unit tests pass.
- no run can violate branch/commit rules.

## Epic 2: API + Queue + Agent Bootstrap

1. Build `POST /run-agent` with validation.
2. Add dedupe fingerprint and lock.
3. Enqueue BullMQ job and start agent.
4. Build status/results/report endpoints.

Acceptance:
- run creation and status retrieval work end-to-end.

## Epic 3: Failure Discovery + Fix Loop

1. Sandbox test execution and parser.
2. Failure normalization and required bug classification.
3. Rule-first fix generation.
4. LLM fallback path.
5. Critic confidence gate.
6. Commit optimizer.

Acceptance:
- deterministic fixtures produce expected bug rows.

## Epic 4: CI Loop + Rollback

1. Poll CI runs.
2. Detect pass/fail/regression.
3. Rollback on regression.
4. Stop on max retries.

Acceptance:
- retry and rollback integration tests pass.

## Epic 5: Dashboard Required Sections

1. Input section with loading state.
2. Run summary card.
3. Score breakdown panel.
4. Fixes table.
5. CI timeline.

Acceptance:
- all required sections visible and accurate in E2E test.

## Epic 6: Advanced Features (optional, flagged)

1. Causal incident graph.
2. Provenance panel.
3. Replay mode.
4. Optional branch tournament.

Acceptance:
- all advanced features disabled by default in contest mode.

## Epic 7: Documentation and Submission Assets

1. Keep docs aligned with SOURCE_OF_TRUTH.
2. Validate README required sections.
3. Final demo script and recording checklist.

Acceptance:
- submission checklist fully green.
