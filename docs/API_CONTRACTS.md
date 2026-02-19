# API and Event Contracts

Canonical source: `SOURCE_OF_TRUTH.md`

This document provides implementation-ready payload schemas for backend and frontend integration.

## 1) Public REST API

## 1.1 POST /run-agent

### Request JSON
```json
{
  "repo_url": "https://github.com/org/repo",
  "team_name": "RIFT ORGANISERS",
  "leader_name": "Saiyam Kumar",
  "requested_ref": "main"
}
```

### Validation Rules
- `repo_url` required, must be valid GitHub HTTPS URL.
- `team_name` required, 1-120 chars.
- `leader_name` required, 1-120 chars.
- `requested_ref` optional, default `main`.

### Response 202 JSON
```json
{
  "run_id": "run_abc123",
  "branch_name": "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
  "status": "queued",
  "socket_room": "/run/run_abc123",
  "fingerprint": "3dc49b..."
}
```

### Response 409 JSON (duplicate active run)
```json
{
  "run_id": "run_existing123",
  "status": "running",
  "message": "Active run already exists for this submission fingerprint"
}
```

## 1.2 GET /agent/status/:runId

### Response 200 JSON
```json
{
  "run_id": "run_abc123",
  "status": "running",
  "current_node": "fix_generator",
  "iteration": 2,
  "max_iterations": 5,
  "progress_pct": 62
}
```

## 1.3 GET /results/:runId

### Response 200 JSON
See `results.json` contract in `SOURCE_OF_TRUTH.md` and `db-architecture.txt`.

## 1.4 GET /report/:runId

### Response 200
- `application/pdf`
- attachment stream

## 1.5 GET /replay/:runId

### Response 200 JSON
```json
{
  "run_id": "run_abc123",
  "events": [
    {
      "step_index": 1,
      "agent_node": "repo_scanner",
      "action_type": "decision",
      "action_label": "repo_safe",
      "payload": {"safe": true},
      "emitted_at": "2026-02-19T10:00:00Z"
    }
  ]
}
```

## 1.6 POST /agent/query

### Request JSON
```json
{
  "run_id": "run_abc123",
  "question": "Why did you fix validator.py first?"
}
```

### Response JSON
```json
{
  "run_id": "run_abc123",
  "answer": "validator.py depended on utils.py failure chain and was fixed after upstream stabilization",
  "evidence": [
    {"step_index": 44, "agent_node": "dependency_mapper"}
  ]
}
```

## 1.7 GET /health

### Response JSON
```json
{
  "gateway": "ok",
  "worker": "ok",
  "agent": "ok",
  "postgres": "ok",
  "redis": "ok",
  "timestamp": "2026-02-19T10:00:00Z"
}
```

## 2) Internal API

## 2.1 POST /agent/start

### Request JSON
```json
{
  "run_id": "run_abc123",
  "repo_url": "https://github.com/org/repo",
  "team_name": "RIFT ORGANISERS",
  "leader_name": "Saiyam Kumar",
  "branch_name": "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
  "max_iterations": 5,
  "feature_flags": {
    "ENABLE_KB_LOOKUP": true,
    "ENABLE_SPECULATIVE_BRANCHES": false,
    "ENABLE_ADVERSARIAL_TESTS": true,
    "ENABLE_CAUSAL_GRAPH": true,
    "ENABLE_PROVENANCE_PASS": true
  }
}
```

### Response JSON
```json
{
  "accepted": true,
  "run_id": "run_abc123"
}
```

## 2.2 GET /agent/status
Internal worker poll endpoint.

## 2.3 GET /agent/stream
SSE thought stream for gateway bridge.

## 3) WebSocket Contract

Room: `/run/:runId`

## 3.1 Event: thought_event
```json
{
  "run_id": "run_abc123",
  "node": "fix_generator",
  "message": "Rule path failed, switching to model route",
  "step_index": 92,
  "timestamp": "2026-02-19T10:03:02Z"
}
```

## 3.2 Event: fix_applied
```json
{
  "run_id": "run_abc123",
  "file": "src/validator.py",
  "bug_type": "SYNTAX",
  "line": 8,
  "status": "applied",
  "confidence": 0.91,
  "commit_sha": "abc123def"
}
```

## 3.3 Event: ci_update
```json
{
  "run_id": "run_abc123",
  "iteration": 2,
  "status": "failed",
  "regression": true,
  "timestamp": "2026-02-19T10:05:12Z"
}
```

## 3.4 Event: telemetry_tick
```json
{
  "run_id": "run_abc123",
  "container_id": "c1",
  "cpu_pct": 42.3,
  "mem_mb": 312,
  "timestamp": "2026-02-19T10:05:13Z"
}
```

## 3.5 Event: run_complete
```json
{
  "run_id": "run_abc123",
  "final_status": "PASSED",
  "score": {
    "base": 100,
    "speed_bonus": 10,
    "efficiency_penalty": 0,
    "total": 110
  },
  "total_time_secs": 244,
  "pdf_url": "/report/run_abc123"
}
```

## 4) Error Envelope Standard

Use this shape for all non-2xx responses:
```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "repo_url must be a valid GitHub URL",
    "details": {
      "field": "repo_url"
    }
  }
}
```

## 5) Backward Compatibility Policy

- Additive changes only for event payloads.
- Do not rename existing keys without version bump.
- Version header for future major changes: `X-API-Version`.
