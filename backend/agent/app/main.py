from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from .errors import install_error_handlers
from .models import AgentStartRequest, AgentStartResponse, AgentStatusResponse
from .state import RunState, run_state_store

app = FastAPI(title="RIFT Agent Service", version="0.1.0")
install_error_handlers(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"agent": "ok", "version": "0.1.0"}


@app.post("/agent/start", response_model=AgentStartResponse)
def agent_start(payload: AgentStartRequest) -> AgentStartResponse:
    run_state_store.upsert(
        RunState(run_id=payload.run_id, status="running", current_node="repo_scanner", iteration=0)
    )
    return AgentStartResponse(accepted=True, run_id=payload.run_id)


@app.get("/agent/status", response_model=AgentStatusResponse)
def agent_status(run_id: str) -> AgentStatusResponse:
    state = run_state_store.get(run_id)
    if state is None:
        return AgentStatusResponse(run_id=run_id, status="queued", current_node="queued", iteration=0)

    return AgentStatusResponse(
        run_id=state.run_id,
        status=state.status,
        current_node=state.current_node,
        iteration=state.iteration,
    )


@app.get("/agent/stream")
def agent_stream(run_id: str) -> StreamingResponse:
    def event_stream() -> str:
        return (
            "event: thought_event\n"
            f"data: {{\"run_id\":\"{run_id}\",\"node\":\"repo_scanner\",\"message\":\"stream initialized\",\"step_index\":1}}\n\n"
        )

    return StreamingResponse(iter([event_stream()]), media_type="text/event-stream")
