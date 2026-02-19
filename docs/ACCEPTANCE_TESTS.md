# Acceptance Tests

This file defines concrete acceptance tests to maximize score and avoid disqualification.

## 1) Compliance Tests

## 1.1 Branch Name Format
Input:
- team: `RIFT ORGANISERS`
- leader: `Saiyam Kumar`
Expected:
- `RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix`

## 1.2 Commit Prefix
Any automated commit message must begin with `[AI-AGENT]`.

## 1.3 Protected Branch Block
Attempted push to `main` or `master` must fail with policy error.

## 2) Required Bug Type Mapping

Given known fixtures, primary fixes table must only use:
- LINTING
- SYNTAX
- LOGIC
- TYPE_ERROR
- IMPORT
- INDENTATION

## 3) Track Example Parity Tests

## Test A
Input failure:
- `src/utils.py` line 15: unused import `os`
Expected row:
- bug_type: `LINTING`
- file: `src/utils.py`
- line: `15`
- fix semantics: remove unused import

## Test B
Input failure:
- `src/validator.py` line 8: missing colon
Expected row:
- bug_type: `SYNTAX`
- file: `src/validator.py`
- line: `8`
- fix semantics: add colon

## 4) API Contract Tests

1. `POST /run-agent` returns 202 and valid room path.
2. `GET /results/:runId` returns schema-valid JSON.
3. `GET /report/:runId` returns pdf stream.
4. `GET /agent/status/:runId` returns current node/iteration.

## 5) Event Contract Tests

Validate payload schema for each event:
- thought_event
- fix_applied
- ci_update
- telemetry_tick
- run_complete

## 6) Retry and Rollback Tests

1. Failed CI with retries left loops back to fix generator.
2. Regression triggers rollback event.
3. Retry count never exceeds configured max.

## 7) Dashboard Required Section Tests

1. Input section present and interactive.
2. Run summary shows required fields.
3. Score panel computes expected formula.
4. Fixes table shows required columns.
5. CI timeline shows iteration and timestamp.

## 8) Artifact Tests

1. Terminal run writes `results.json`.
2. `results.json` schema valid.
3. PDF report endpoint available.

## 9) Performance/Score Tests

1. Runtime under 5 minutes yields speed bonus.
2. Commit count over 20 applies penalty exactly.

## 10) No-Intervention Tests

1. Run can complete from trigger to terminal state without manual patching.
2. No human edits to target repo during run.
