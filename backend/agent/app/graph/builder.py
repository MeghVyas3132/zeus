"""
LangGraph graph builder — wires all nodes with conditional edges.

Graph flow:
  repo_scanner → test_runner → ast_analyzer → [should_fix?]
      YES → fix_generator → commit_push → [should_monitor_ci?]
          YES → ci_monitor → [should_retry?]
              "no_ci"  → ci_workflow_creator → ci_monitor (one-time loop)
              "retry"  → increment_iteration → test_runner (loop)
              "scorer" → scorer → END
          NO → scorer → END
      NO → scorer → END
"""
from __future__ import annotations

import logging
import time
from typing import Any, Literal

from langgraph.graph import END, StateGraph  # type: ignore[import-untyped]

from ..config import MAX_ITERATIONS
from ..db import insert_trace, update_run_status
from ..events import emit_status_update, emit_thought
from .state import AgentState
from .nodes.repo_scanner import repo_scanner
from .nodes.test_runner import test_runner
from .nodes.ast_analyzer import ast_analyzer
from .nodes.fix_generator import fix_generator
from .nodes.commit_push import commit_push
from .nodes.ci_monitor import ci_monitor
from .nodes.ci_workflow_creator import ci_workflow_creator
from .nodes.scorer import scorer

logger = logging.getLogger("rift.graph")


# ── Increment iteration (thin transition node) ─────────────

async def increment_iteration(state: AgentState) -> AgentState:
    """Bump iteration counter before next test cycle."""
    iteration = state.get("iteration", 1) + 1
    run_id = state["run_id"]

    await emit_thought(
        run_id, "retry",
        f"Starting iteration {iteration}…",
        iteration * 10,
    )
    await emit_status_update(run_id, "running", "test_runner", iteration)

    return {"iteration": iteration, "current_node": "retry"}


# ── Conditional edge: should we keep iterating? ─────────────

def should_retry(state: AgentState) -> Literal["retry", "scorer", "create_workflow"]:
    """
    After ci_monitor, decide:
      - If CI status is "no_ci" and we haven't created a workflow yet →
        route to ci_workflow_creator (one-time).
      - If CI passed AND local tests passed → scorer (done).
      - If quarantined → scorer (done).
      - If we still have iterations left and no quarantine → retry.
      - Otherwise → scorer.
    """
    ci_status = state.get("current_ci_status", "failed")
    test_exit = state.get("test_exit_code", 1)
    iteration = state.get("iteration", 1)
    max_iter = state.get("max_iterations", MAX_ITERATIONS)
    quarantine = state.get("quarantine_reason")
    workflow_created = state.get("ci_workflow_created", False)

    # No CI workflow detected — create one (once)
    if ci_status == "no_ci" and not workflow_created:
        return "create_workflow"

    # If we already created a workflow but CI still says no_ci / failed,
    # treat it like a normal failure for retry logic
    if ci_status == "passed" and test_exit == 0:
        return "scorer"
    if quarantine:
        return "scorer"
    if iteration >= max_iter:
        return "scorer"

    return "retry"


def should_fix(state: AgentState) -> Literal["fix_generator", "scorer"]:
    """
    After ast_analyzer, decide if there are failures to fix.
    If tests passed (no failures), go straight to scorer.
    """
    failures = state.get("failures", [])
    exit_code = state.get("test_exit_code", 1)

    if exit_code == 0 or not failures:
        return "scorer"
    return "fix_generator"


def should_monitor_ci(state: AgentState) -> Literal["ci_monitor", "scorer"]:
    """
    After commit_push, decide whether to poll CI.
    If push failed (error_message set, no commit_sha on fixes), skip CI
    and go straight to scorer — no point polling for a push that didn't land.
    """
    error = state.get("error_message", "")
    if error and "commit/push failed" in error.lower():
        return "scorer"
    # Monitor CI only if this iteration pushed a fresh commit.
    if not state.get("pushed_this_iteration", False):
        return "scorer"
    return "ci_monitor"


# ── Build the graph ─────────────────────────────────────────

def build_agent_graph() -> Any:
    """
    Construct and compile the LangGraph StateGraph.
    Returns a compiled graph that can be invoked with `graph.ainvoke(state)`.
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("repo_scanner", repo_scanner)
    graph.add_node("test_runner", test_runner)
    graph.add_node("ast_analyzer", ast_analyzer)
    graph.add_node("fix_generator", fix_generator)
    graph.add_node("commit_push", commit_push)
    graph.add_node("ci_monitor", ci_monitor)
    graph.add_node("ci_workflow_creator", ci_workflow_creator)
    graph.add_node("scorer", scorer)
    graph.add_node("increment_iteration", increment_iteration)

    # Set entry point
    graph.set_entry_point("repo_scanner")

    # Linear edges
    graph.add_edge("repo_scanner", "test_runner")
    graph.add_edge("test_runner", "ast_analyzer")

    # Conditional: after analysis, fix or score
    graph.add_conditional_edges(
        "ast_analyzer",
        should_fix,
        {
            "fix_generator": "fix_generator",
            "scorer": "scorer",
        },
    )

    graph.add_edge("fix_generator", "commit_push")

    # Conditional: after push, monitor CI or skip to scorer
    graph.add_conditional_edges(
        "commit_push",
        should_monitor_ci,
        {
            "ci_monitor": "ci_monitor",
            "scorer": "scorer",
        },
    )

    # Conditional: after CI, retry / create workflow / score
    graph.add_conditional_edges(
        "ci_monitor",
        should_retry,
        {
            "retry": "increment_iteration",
            "create_workflow": "ci_workflow_creator",
            "scorer": "scorer",
        },
    )

    # After creating a CI workflow, go back to ci_monitor to poll the real run
    graph.add_edge("ci_workflow_creator", "ci_monitor")

    # Retry loop → back to test_runner
    graph.add_edge("increment_iteration", "test_runner")

    # Terminal
    graph.add_edge("scorer", END)

    return graph.compile()


# ── Recursion limit ─────────────────────────────────────────
# Each iteration visits ~7 nodes. With MAX_ITERATIONS=5 that's ~35 steps.
# Add generous headroom for conditional edges and safety margin.
_RECURSION_LIMIT = 100


# ── Runner function ─────────────────────────────────────────

async def run_agent_graph(
    run_id: str,
    repo_url: str,
    team_name: str,
    leader_name: str,
    branch_name: str,
    max_iterations: int,
    feature_flags: dict[str, bool],
) -> AgentState:
    """
    Execute the full agent graph for a run.
    Called from main.py's /agent/start endpoint.
    """
    logger.info("Starting agent graph for run %s", run_id)

    # Update DB to running
    await update_run_status(run_id, "running")
    await emit_status_update(run_id, "running", "repo_scanner", 0)

    initial_state: AgentState = {
        "run_id": run_id,
        "repo_url": repo_url,
        "team_name": team_name,
        "leader_name": leader_name,
        "branch_name": branch_name,
        "max_iterations": max_iterations,
        "feature_flags": feature_flags,
        "iteration": 1,
        "current_node": "repo_scanner",
        "status": "running",
        "fixes": [],
        "ci_runs": [],
        "total_commits": 0,
        "pushed_this_iteration": False,
        "start_time": time.time(),
    }

    graph = build_agent_graph()

    try:
        final_state = await graph.ainvoke(
            initial_state,
            config={"recursion_limit": _RECURSION_LIMIT},
        )
    except Exception as exc:
        logger.exception("Agent graph failed for run %s", run_id)
        await update_run_status(run_id, "failed")
        await emit_status_update(run_id, "failed", "error", 0)
        await emit_thought(run_id, "error", f"Agent crashed: {exc}", 999)
        raise

    logger.info("Agent graph completed for run %s — status=%s", run_id, final_state.get("status"))
    return final_state
