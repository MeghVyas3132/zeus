# Operations Runbook

## 1) Services

- Frontend
- Gateway
- Worker
- Agent
- PostgreSQL
- Redis

## 2) Startup Order

1. PostgreSQL
2. Redis
3. Agent service
4. Gateway + worker
5. Frontend

## 3) Health Checks

- Gateway: `GET /health`
- Agent: internal health endpoint
- Redis: ping
- PostgreSQL: simple select

## 4) Common Incidents

## Incident: Run stuck in queued
Checks:
1. Worker process running?
2. BullMQ queue has active consumers?
3. Redis connectivity valid?

## Incident: Run stuck in running
Checks:
1. Agent node transitions updating?
2. CI poller receiving statuses?
3. Retry cap reached?

## Incident: Missing results.json
Checks:
1. Terminal status reached?
2. outputs path writable?
3. schema validation errors in logs?

## 5) Recovery Actions

1. Restart worker if queue consumer dead.
2. Requeue failed jobs from dead-letter queue if safe.
3. Mark orphaned runs failed with reason and emit terminal event.

## 6) Logging Conventions

Every log line should include:
- run_id
- service
- node (if agent)
- action
- status

## 7) Contest Mode Defaults

For reliability in judging:
- disable speculative branches
- enable deterministic rule-first path
- keep optional features behind flags
