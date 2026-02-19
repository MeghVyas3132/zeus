# Worker Service

This service will host BullMQ consumers that orchestrate:
- run bootstrap
- agent start calls
- status polling
- artifact finalization

Phase 1 intentionally keeps worker logic out until queue wiring in Phase B.
