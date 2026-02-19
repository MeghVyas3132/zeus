from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.main import app


client = TestClient(app)


def test_agent_start_rejects_invalid_payload_with_envelope() -> None:
    response = client.post("/agent/start", json={"run_id": "run_1"})

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_INPUT"
    assert body["error"]["message"] == "Request payload validation failed"


def test_agent_start_accepts_valid_payload() -> None:
    response = client.post(
        "/agent/start",
        json={
            "run_id": "run_abc123",
            "repo_url": "https://github.com/org/repo",
            "team_name": "RIFT ORGANISERS",
            "leader_name": "Saiyam Kumar",
            "branch_name": "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
            "max_iterations": 5,
            "feature_flags": {
                "ENABLE_KB_LOOKUP": True,
                "ENABLE_SPECULATIVE_BRANCHES": False,
                "ENABLE_ADVERSARIAL_TESTS": True,
                "ENABLE_CAUSAL_GRAPH": True,
                "ENABLE_PROVENANCE_PASS": True,
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": True, "run_id": "run_abc123"}


def test_agent_status_returns_running_after_start() -> None:
    start_response = client.post(
        "/agent/start",
        json={
            "run_id": "run_status_1",
            "repo_url": "https://github.com/org/repo",
            "team_name": "RIFT ORGANISERS",
            "leader_name": "Saiyam Kumar",
            "branch_name": "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
            "max_iterations": 5,
            "feature_flags": {
                "ENABLE_KB_LOOKUP": True,
                "ENABLE_SPECULATIVE_BRANCHES": False,
                "ENABLE_ADVERSARIAL_TESTS": True,
                "ENABLE_CAUSAL_GRAPH": True,
                "ENABLE_PROVENANCE_PASS": True,
            },
        },
    )
    assert start_response.status_code == 200

    status_response = client.get("/agent/status", params={"run_id": "run_status_1"})
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "running"
    assert status_response.json()["current_node"] == "repo_scanner"


def test_agent_stream_emits_sse_payload() -> None:
    response = client.get("/agent/stream", params={"run_id": "run_stream_1"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "thought_event" in response.text
