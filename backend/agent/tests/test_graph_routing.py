from __future__ import annotations

from app.graph.builder import should_monitor_ci


def test_should_monitor_ci_skips_when_push_failed() -> None:
    assert should_monitor_ci({"error_message": "Git commit/push failed: auth error"}) == "scorer"


def test_should_monitor_ci_skips_when_no_new_push_in_iteration() -> None:
    assert should_monitor_ci({"pushed_this_iteration": False}) == "scorer"


def test_should_monitor_ci_runs_when_iteration_pushed_commit() -> None:
    assert should_monitor_ci({"pushed_this_iteration": True}) == "ci_monitor"
