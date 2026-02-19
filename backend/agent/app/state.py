from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Literal


RunStatus = Literal["queued", "running", "passed", "failed", "quarantined"]


@dataclass
class RunState:
    run_id: str
    status: RunStatus
    current_node: str
    iteration: int


class InMemoryRunStateStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[str, RunState] = {}

    def upsert(self, state: RunState) -> None:
        with self._lock:
            self._runs[state.run_id] = state

    def get(self, run_id: str) -> RunState | None:
        with self._lock:
            return self._runs.get(run_id)


run_state_store = InMemoryRunStateStore()
